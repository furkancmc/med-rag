from collections.abc import Iterator

from medrag.llm import EvrenLLM
from medrag.retrieve import Hit, Retriever

from .prompt import DISCLAIMER, REWRITE_PROMPT, build_messages
from .triage import EMERGENCY_MESSAGE, check_emergency


def source_card(n: int, hit: Hit) -> dict:
    c = hit.chunk
    return {
        "n": n,
        "title": c["title"],
        "section": c["section"],
        "url": c["url"],
        "source": c["source"],
        "license": c["license"],
        "snippet": c["text"][:200],
        "text": c["text"],
    }


class ChatService:
    def __init__(self, retriever: Retriever, llm: EvrenLLM, top_k: int = 5):
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k

    def rewrite_query(self, question: str, history: list[dict]) -> str:
        """Geçmiş varsa takip sorusunu tek başına anlaşılır arama sorgusuna çevirir."""
        if not history:
            return question
        lines = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-4:])
        prompt = REWRITE_PROMPT.format(history=lines, question=question)
        try:
            rewritten = self.llm.complete(
                [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=80
            )
        except RuntimeError:
            return question
        return rewritten.splitlines()[0].strip() if rewritten else question

    def stream(self, question: str, history: list[dict] | None = None) -> Iterator[dict]:
        """Olayları sırayla üretir: emergency?, sources, token..., done."""
        history = history or []
        triage = check_emergency(question)
        if triage.emergency:
            yield {"type": "emergency", "text": EMERGENCY_MESSAGE, "reasons": triage.reasons}

        hits = self.retriever.search(self.rewrite_query(question, history), k=self.top_k)
        yield {"type": "sources", "items": [source_card(n, h) for n, h in enumerate(hits, 1)]}

        messages = build_messages(question, history, hits, emergency=triage.emergency)
        for piece in self.llm.stream(messages):
            yield {"type": "token", "text": piece}
        yield {"type": "token", "text": "\n\n" + DISCLAIMER}
        yield {"type": "done"}

    def answer(self, question: str, history: list[dict] | None = None) -> dict:
        """Akışı toplayıp tek cevap olarak döner (test ve değerlendirme için)."""
        out = {"text": "", "sources": [], "sources_text": "", "emergency": False}
        for ev in self.stream(question, history):
            if ev["type"] == "emergency":
                out["emergency"] = True
                out["emergency_text"] = ev["text"]
            elif ev["type"] == "sources":
                out["sources"] = ev["items"]
                out["sources_text"] = "\n\n".join(f"[{s['n']}] {s['title']}: {s['text']}" for s in ev["items"])
            elif ev["type"] == "token":
                out["text"] += ev["text"]
        return out
