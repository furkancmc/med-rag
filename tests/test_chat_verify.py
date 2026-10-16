import threading
import time

from medrag.chat.prompt import DISCLAIMER
from medrag.chat.service import ChatService, source_card
from medrag.chat.verify import AnswerVerifier, parse_verdicts
from medrag.retrieve import Hit

CHUNK = {"id": "d1#0", "doc_id": "d1", "title": "Grip", "section": "Belirtiler",
         "text": "Grip ateş ve öksürük yapar.", "source": "wikipedia", "lang": "tr",
         "url": "https://tr.wikipedia.org/wiki/Grip", "license": "CC BY-SA 4.0"}
ANSWER = "Grip ateş ve öksürük yapabilir [1]. Grip her zaman antibiyotikle geçer [1]. Belirtiler sürerse bir hekime danışmanız önerilir."
CARDS = [{"n": 1, "title": "Grip", "text": CHUNK["text"]}]


class Judge:
    def __init__(self, reply="1: DESTEKLİ\n2: DESTEKSİZ - kaynakta antibiyotik yok\n3: DESTEKLİ", delay=0.0):
        self.reply, self.delay, self.prompts = reply, delay, []

    def complete(self, messages, temperature=0.3, max_tokens=1024):
        self.prompts.append(messages[0]["content"])
        time.sleep(self.delay)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class Retriever:
    def search(self, query, k=5, mode="hybrid"):
        return [Hit(CHUNK, 1.0)]


class AnswerLLM:
    def __init__(self, text=ANSWER):
        self.text = text

    def complete(self, messages, temperature=0.3, max_tokens=1024):
        return "x"

    def stream(self, messages, temperature=0.3, max_tokens=1024):
        yield self.text


def test_parse_verdicts_tolerant():
    text = "**1:** DESTEKLİ\n2) desteksiz - çelişiyor\n- 3. Desteksiz: uydurma\nalakasız satır"
    got = parse_verdicts(text)
    assert got[1] == (True, "") and got[2] == (False, "çelişiyor") and got[3] == (False, "uydurma")


def test_verify_flags_unsupported_sentences():
    res = AnswerVerifier(Judge(), group_size=5).verify(ANSWER, CARDS)
    assert res.checked == 3 and res.error is None
    assert [u["sentence"] for u in res.unsupported] == ["Grip her zaman antibiyotikle geçer [1]."]
    assert "antibiyotik" in res.unsupported[0]["reason"]


def test_verify_groups_run_concurrently_and_keep_order():
    judge = Judge(delay=0.3, reply="1: DESTEKLİ\n2: DESTEKLİ\n3: DESTEKLİ")
    start = time.time()
    res = AnswerVerifier(judge, group_size=1, concurrency=4).verify(ANSWER, CARDS)
    assert len(judge.prompts) == 3 and time.time() - start < 0.8
    # Her grup kendi numarasını görür; gruplarda 1 numaralı cümleden başka yanıt gelmez.
    assert res.checked >= 1


def test_verify_timeout_returns_error_without_blocking():
    gate = threading.Event()

    class Slow(Judge):
        def complete(self, *a, **k):
            gate.wait(5)
            return "1: DESTEKLİ"

    start = time.time()
    res = AnswerVerifier(Slow(), budget=0.2).verify(ANSWER, CARDS)
    gate.set()
    assert time.time() - start < 1.5
    assert res.checked == 0 and res.error == "zaman aşımı"
    assert res.event() == {"type": "verification", "checked": 0, "unsupported": [], "error": "zaman aşımı"}


def test_verify_judge_error_is_tolerated():
    res = AnswerVerifier(Judge(reply=RuntimeError("x"))).verify(ANSWER, CARDS)
    assert res.checked == 0 and res.error == "RuntimeError"


def test_should_skip():
    v = AnswerVerifier(Judge())
    assert v.should_skip("Merhaba!", CARDS)
    assert v.should_skip(ANSWER, [])
    assert not v.should_skip(ANSWER, CARDS)


def test_service_emits_verification_before_disclaimer():
    svc = ChatService(Retriever(), AnswerLLM(), verifier=AnswerVerifier(Judge(), group_size=5))
    events = list(svc.stream("Grip nedir?"))
    kinds = [e["type"] for e in events]
    i = kinds.index("verification")
    assert kinds[:1] == ["sources"] and kinds[i - 1] == "token" and kinds[i + 1 :] == ["token", "done"]
    ver = events[i]
    assert ver["checked"] == 3 and len(ver["unsupported"]) == 1
    assert DISCLAIMER in events[i + 1]["text"]


def test_service_skips_verification_for_emergency_and_offtopic():
    svc = ChatService(Retriever(), AnswerLLM(), verifier=AnswerVerifier(Judge()))
    kinds = [e["type"] for e in svc.stream("nefes alamıyorum")]
    assert "verification" not in kinds
    off = AnswerLLM("Ben yalnızca sağlık konularında yardımcı olabiliyorum; sağlıkla ilgili bir sorunuz varsa yanıtlarım.")
    svc = ChatService(Retriever(), off, verifier=AnswerVerifier(Judge()))
    assert "verification" not in [e["type"] for e in svc.stream("Bitcoin almalı mıyım?")]


def test_service_verifier_failure_does_not_break_stream():
    svc = ChatService(Retriever(), AnswerLLM(), verifier=AnswerVerifier(Judge(reply=RuntimeError("x"))))
    events = list(svc.stream("Grip nedir?"))
    assert events[-1]["type"] == "done"
    assert next(e for e in events if e["type"] == "verification")["error"]


def test_source_card_passes_optional_metadata():
    card = source_card(1, Hit({**CHUNK, "published": "2024-05-01", "retrieved_at": "2026-01-02"}, 1.0))
    assert card["published"] == "2024-05-01" and card["retrieved_at"] == "2026-01-02"
    assert "published" not in source_card(1, Hit(CHUNK, 1.0))
