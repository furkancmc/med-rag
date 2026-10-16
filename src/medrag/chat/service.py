import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from medrag.config import Settings, get_settings
from medrag.llm import EvrenLLM, parse_extra_params
from medrag.retrieve import Hit, Retriever

from .classifier import Classification, SafetyClassifier
from .guard import DiagnosisGuard, DoseGuard, GuardChain
from .prompt import DISCLAIMER, REWRITE_PROMPT, build_messages
from .triage import (
    EMERGENCY_MESSAGE,
    HARMFUL_RESPONSE,
    SELF_HARM_RESPONSE,
    SENSITIVE_NOTE,
    check_emergency,
    is_self_harm,
)
from .verify import AnswerVerifier

AUTO = "auto"  # classifier/verifier: ayarlardan kur (yalnızca gerçek EvrenLLM ile)
OFFTOPIC_MARK = "Ben yalnızca sağlık konularında"


def source_card(n: int, hit: Hit) -> dict:
    c = hit.chunk
    card = {
        "n": n,
        "title": c["title"],
        "section": c["section"],
        "url": c["url"],
        "source": c["source"],
        "license": c["license"],
        "snippet": c["text"][:200],
        "text": c["text"],
    }
    for key in ("published", "retrieved_at"):  # veri iş akışı ekler; eski indekslerde olmayabilir
        if c.get(key):
            card[key] = c[key]
    return card


def _side_llm(llm: EvrenLLM, model: str, extra: str) -> EvrenLLM:
    # Yan işler (sınıflandırma, doğrulama) kısa ve hızlı olmalı: az yeniden deneme, kısa zaman aşımı.
    return llm.with_model(model, extra_params=parse_extra_params(extra), timeout=30.0, max_retries=2, backoff=1.0)


def build_classifier(llm: EvrenLLM, s: Settings) -> SafetyClassifier | None:
    if not s.classifier_enabled:
        return None
    guard = _side_llm(llm, s.guard_model, "") if s.guard_model else None
    judge = _side_llm(llm, s.classifier_model, s.classifier_extra_params) if s.classifier_model else None
    classifier = SafetyClassifier(guard, judge)
    return classifier if classifier.enabled else None


def build_verifier(llm: EvrenLLM, s: Settings) -> AnswerVerifier | None:
    if not s.verify_enabled or not s.verify_model:
        return None
    return AnswerVerifier(
        _side_llm(llm, s.verify_model, s.verify_extra_params),
        budget=s.verify_budget_seconds,
        group_size=s.verify_group_size,
        concurrency=s.verify_concurrency,
    )


class ChatService:
    def __init__(
        self,
        retriever: Retriever,
        llm: Any,
        top_k: int = 5,
        *,
        classifier: SafetyClassifier | None | str = AUTO,
        verifier: AnswerVerifier | None | str = AUTO,
        settings: Settings | None = None,
        classifier_timeout: float | None = None,
        answer_max_tokens: int | None = None,
    ):
        real = isinstance(llm, EvrenLLM)
        s = settings or (get_settings() if real else None)
        if real and s is not None:
            extra = parse_extra_params(s.llm_extra_params)
            if extra and not llm.extra_params:
                llm = llm.with_model(llm.model, extra_params=extra, timeout=llm.timeout)
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k
        self.classifier = build_classifier(llm, s) if classifier == AUTO and real and s else (
            None if classifier == AUTO else classifier
        )
        self.verifier = build_verifier(llm, s) if verifier == AUTO and real and s else (
            None if verifier == AUTO else verifier
        )
        self.classifier_timeout = classifier_timeout or (s.classifier_timeout_seconds if s else 8.0)
        self.answer_max_tokens = answer_max_tokens or (s.answer_max_tokens if s else 4096)
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="medrag-chat")

    def rewrite_query(self, question: str, history: list[dict]) -> str:
        """Geçmiş varsa takip sorusunu tek başına anlaşılır arama sorgusuna çevirir."""
        if not history:
            return question
        lines = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-4:])
        prompt = REWRITE_PROMPT.format(history=lines, question=question)
        try:
            rewritten = self.llm.complete(
                [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=600
            )
        except RuntimeError:
            return question
        return rewritten.splitlines()[0].strip() if rewritten else question

    def _classify(self, question: str, history: list[dict]) -> Future[Classification] | None:
        if self.classifier is None:
            return None
        return self._pool.submit(self.classifier.classify, question, history)

    def _await_classification(self, future: Future[Classification] | None) -> Classification:
        """Sınıflandırıcıyı en fazla `classifier_timeout` bekler; hata ve zaman aşımında bulgu yok sayılır."""
        if future is None:
            return Classification()
        try:
            return future.result(timeout=self.classifier_timeout)
        except Exception:  # noqa: BLE001 - sınıflandırıcı yalnızca ekleyebilir; hata kural kararını bozmaz
            return Classification(errors=["zaman aşımı veya hata"])

    def stream(self, question: str, history: list[dict] | None = None) -> Iterator[dict]:
        """Olayları sırayla üretir: emergency?, sources, token..., verification?, token (uyarı), done.

        Sınıflandırıcı arama ile eş zamanlı çalışır; kuralların bulamadığı bir acil durumu bulursa
        `emergency` olayı `sources`'tan hemen önce (yine ilk cevap parçasından önce) gelir.
        """
        history = history or []
        triage = check_emergency(question)
        reasons = list(triage.reasons)
        if triage.emergency:
            yield {"type": "emergency", "text": EMERGENCY_MESSAGE, "reasons": reasons}
        pending = self._classify(question, history)

        direct = is_self_harm(reasons)  # kendine zarar kuralı kesin: aramaya ve modele gerek yok
        hits = [] if direct else self.retriever.search(self.rewrite_query(question, history), k=self.top_k)
        cls = self._await_classification(pending)
        direct = direct or cls.self_harm
        emergency = triage.emergency or cls.emergency
        if cls.emergency and not triage.emergency:
            reasons = cls.reasons or ["yapay zekâ sınıflandırıcısı"]
            yield {"type": "emergency", "text": EMERGENCY_MESSAGE, "reasons": reasons}

        cards = [] if direct else [source_card(n, h) for n, h in enumerate(hits, 1)]
        yield {"type": "sources", "items": cards}

        if direct:
            yield {"type": "token", "text": SELF_HARM_RESPONSE}
            yield {"type": "token", "text": "\n\n" + DISCLAIMER}
            yield {"type": "done"}
            return

        messages = build_messages(
            question, history, hits, emergency=emergency, extra_note=SENSITIVE_NOTE if cls.harmful else ""
        )
        guards = [DoseGuard()] + ([DiagnosisGuard()] if emergency else [])
        guard = GuardChain(*guards)
        answer = ""
        for piece in self.llm.stream(messages, max_tokens=self.answer_max_tokens):
            safe = guard.feed(piece)
            if safe:
                answer += safe
                yield {"type": "token", "text": safe}
        tail = guard.flush()
        if tail:
            answer += tail
            yield {"type": "token", "text": tail}
        if not answer.strip():
            answer = HARMFUL_RESPONSE if cls.harmful else EMERGENCY_MESSAGE if emergency else ""
            if answer:
                yield {"type": "token", "text": answer}

        verifiable = self.verifier is not None and not emergency and OFFTOPIC_MARK not in answer
        if verifiable and not self.verifier.should_skip(answer, cards):
            yield self.verifier.verify(answer, cards).event()

        yield {"type": "token", "text": "\n\n" + DISCLAIMER}
        yield {"type": "done"}

    def answer(self, question: str, history: list[dict] | None = None) -> dict:
        """Akışı toplayıp tek cevap olarak döner (test ve değerlendirme için)."""
        out: dict[str, Any] = {
            "text": "", "sources": [], "sources_text": "", "emergency": False, "verification": None,
        }
        start = time.monotonic()
        for ev in self.stream(question, history):
            if ev["type"] == "token" and "first_token_s" not in out:
                out["first_token_s"] = time.monotonic() - start
            if ev["type"] == "emergency":
                out["emergency"] = True
                out["emergency_text"] = ev["text"]
                out["emergency_reasons"] = ev.get("reasons", [])
            elif ev["type"] == "sources":
                out["sources"] = ev["items"]
                out["sources_text"] = "\n\n".join(f"[{s['n']}] {s['title']}: {s['text']}" for s in ev["items"])
            elif ev["type"] == "token":
                out["text"] += ev["text"]
            elif ev["type"] == "verification":
                out["verification"] = ev
        out["total_s"] = time.monotonic() - start
        return out
