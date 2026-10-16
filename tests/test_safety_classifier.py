import threading
import time

from medrag.chat.classifier import SafetyClassifier, parse_emergency, parse_guard
from medrag.chat.prompt import DISCLAIMER
from medrag.chat.service import ChatService
from medrag.chat.triage import SELF_HARM_RESPONSE
from medrag.retrieve import Hit

CHUNK = {"id": "d1#0", "doc_id": "d1", "title": "Grip", "section": "Belirtiler",
         "text": "Grip ateş yapar.", "source": "wikipedia", "lang": "tr",
         "url": "https://x/Grip", "license": "CC BY-SA 4.0"}


class Fake:
    """complete() sabit bir çıktı (ya da istisna) döner; çağrı sayar."""

    def __init__(self, reply="", delay=0.0):
        self.reply, self.delay, self.calls = reply, delay, 0

    def complete(self, messages, temperature=0.3, max_tokens=1024):
        self.calls += 1
        time.sleep(self.delay)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class Retriever:
    def __init__(self, delay=0.0):
        self.delay, self.queries = delay, []

    def search(self, query, k=5, mode="hybrid"):
        self.queries.append(query)
        time.sleep(self.delay)
        return [Hit(CHUNK, 1.0)]


class AnswerLLM:
    def __init__(self, text="Grip ateş yapar [1]."):
        self.text, self.messages = text, []

    def complete(self, messages, temperature=0.3, max_tokens=1024):
        return "q"

    def stream(self, messages, temperature=0.3, max_tokens=1024):
        self.messages.append(messages)
        yield self.text


def test_parse_guard_variants():
    assert parse_guard("Safety: Unsafe\nCategories: Suicide & Self-Harm") == ("unsafe", ["suicide & self-harm"])
    assert parse_guard("Safety: Safe\nCategories: None") == ("safe", [])
    assert parse_guard("safety:controversial\ncategory: Violent, Jailbreak") == ("controversial", ["violent", "jailbreak"])
    assert parse_guard("**Safety:** Unsafe") == ("unsafe", [])
    assert parse_guard("anlaşılmaz çıktı") == ("", [])


def test_parse_emergency():
    assert parse_emergency("ACIL: EVET\nKENDINE_ZARAR: HAYIR") == (True, False)
    assert parse_emergency("ACİL: hayır\nKENDİNE_ZARAR: evet") == (False, True)
    assert parse_emergency("bilmiyorum") == (None, None)


def test_classifier_combines_sources_and_tolerates_errors():
    guard = Fake("Safety: Unsafe\nCategories: Violent")
    llm = Fake("ACIL: EVET\nKENDINE_ZARAR: HAYIR")
    res = SafetyClassifier(guard, llm).classify("soru")
    assert res.emergency and res.harmful and not res.self_harm
    bad = SafetyClassifier(Fake(RuntimeError("x")), Fake("çöp")).classify("soru")
    assert not bad.emergency and not bad.harmful and bad.errors
    sh = SafetyClassifier(Fake("Safety: Unsafe\nCategories: Suicide & Self-Harm"), None).classify("soru")
    assert sh.self_harm and sh.emergency


def make(classifier, retriever=None, llm=None, timeout=2.0):
    return ChatService(retriever or Retriever(), llm or AnswerLLM(), classifier=classifier,
                       verifier=None, classifier_timeout=timeout)


def test_classifier_adds_emergency_before_sources_and_tokens():
    svc = make(SafetyClassifier(None, Fake("ACIL: EVET\nKENDINE_ZARAR: HAYIR")))
    events = list(svc.stream("2 aylık bebeğimin ateşi 38.5"))
    assert [e["type"] for e in events][:3] == ["emergency", "sources", "token"]
    assert events[0]["reasons"] and "112" in events[0]["text"]


def test_classifier_cannot_remove_rule_emergency():
    svc = make(SafetyClassifier(None, Fake("ACIL: HAYIR\nKENDINE_ZARAR: HAYIR")))
    events = list(svc.stream("nefes alamıyorum"))
    assert [e["type"] for e in events].count("emergency") == 1 and events[0]["type"] == "emergency"


def test_classifier_runs_concurrently_with_retrieval():
    slow = Fake("ACIL: HAYIR\nKENDINE_ZARAR: HAYIR", delay=0.4)
    svc = make(SafetyClassifier(None, slow), retriever=Retriever(delay=0.4))
    start = time.time()
    list(svc.stream("Grip nedir?"))
    assert time.time() - start < 0.75  # ardışık olsaydı >= 0.8 s


def test_classifier_timeout_does_not_block_answer():
    gate = threading.Event()

    class Hang(Fake):
        def complete(self, *a, **k):
            gate.wait(5)
            return "ACIL: EVET"

    svc = make(SafetyClassifier(None, Hang()), timeout=0.2)
    start = time.time()
    events = list(svc.stream("Grip nedir?"))
    gate.set()
    assert time.time() - start < 1.5 and events[-1]["type"] == "done"
    assert "emergency" not in [e["type"] for e in events]


def test_self_harm_by_rule_skips_model_and_retrieval():
    retriever, llm = Retriever(), AnswerLLM()
    events = list(make(None, retriever, llm).stream("Kendimi öldürmek istiyorum"))
    assert [e["type"] for e in events] == ["emergency", "sources", "token", "token", "done"]
    assert events[1]["items"] == [] and events[2]["text"] == SELF_HARM_RESPONSE
    assert DISCLAIMER in events[3]["text"] and not retriever.queries and not llm.messages


def test_indirect_self_harm_by_classifier_gets_safe_response():
    guard = Fake("Safety: Unsafe\nCategories: Suicide & Self-Harm")
    events = list(make(SafetyClassifier(guard, None)).stream("hepsi çok anlamsız geliyor"))
    assert events[0]["type"] == "emergency"
    assert "".join(e.get("text", "") for e in events if e["type"] == "token").startswith(SELF_HARM_RESPONSE)


def test_indirect_self_harm_phrases_caught_by_rules():
    for text in ["Hepsini bitirsem herkes rahat eder", "Yok olmak istiyorum"]:
        assert next(iter(make(None).stream(text)))["type"] == "emergency"


def test_harmful_request_adds_safety_note_to_prompt():
    llm = AnswerLLM()
    svc = make(SafetyClassifier(Fake("Safety: Unsafe\nCategories: Violent"), None), llm=llm)
    list(svc.stream("Birine zarar vermek için ilaç"))
    assert "zararlı olabilecek bir istek" in llm.messages[0][0]["content"]


def test_emergency_answer_drops_diagnosis_names_and_is_never_empty():
    llm = AnswerLLM("Bu kalp krizi olabilir [1]. Hemen 112'yi arayın [1].")
    events = list(make(None, llm=llm).stream("Göğsümde baskı var, kolum uyuşuyor"))
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert "kalp krizi" not in text and "112" in text
    only_diag = AnswerLLM("Bu bir kalp krizidir.")
    events = list(make(None, llm=only_diag).stream("nefes alamıyorum"))
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert "kalp krizi" not in text and "112" in text
