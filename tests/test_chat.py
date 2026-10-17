import pytest

from medrag.chat.prompt import DISCLAIMER, build_messages
from medrag.chat.service import ChatService
from medrag.chat.triage import check_emergency
from medrag.retrieve import Hit

CHUNK = {"id": "d1#0", "doc_id": "d1", "title": "Grip", "section": "Belirtiler",
         "text": "Grip ateş ve öksürük yapar.", "source": "wikipedia", "lang": "tr",
         "url": "https://tr.wikipedia.org/wiki/Grip", "license": "CC BY-SA 4.0"}


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def search(self, query, k=5, mode="hybrid"):
        self.queries.append(query)
        return [Hit(CHUNK, 1.0)]


class FakeLLM:
    def __init__(self):
        self.calls = []

    def complete(self, messages, temperature=0.3, max_tokens=1024):
        return "grip belirtileri"

    def stream(self, messages, temperature=0.3, max_tokens=1024):
        self.calls.append(messages)
        yield "Grip ateşle başlar [1]."


@pytest.mark.parametrize("text", [
    "Göğsümde şiddetli bir ağrı var, sol koluma yayılıyor",
    "göğüs ağrım ve baskı hissi var",
    "Babamın yüzü bir yana kaydı ve konuşması bozuldu",
    "nefes alamıyorum",
    "Annem bayıldı uyandıramıyorum",
    "Çocuk yanlışlıkla fazla ilaç içti",
    "dilim ve boğazım şişiyor",
    "kendimi öldürmek istiyorum",
    "çocuğum havale geçiriyor",
])
def test_emergency_detected(text):
    assert check_emergency(text).emergency


@pytest.mark.parametrize("text", [
    "Grip belirtileri nelerdir?",
    "Diyabet için hangi besinleri yemeliyim?",
    "Kolesterol nedir",
    "Migren ağrısı kaç saat sürer",
])
def test_normal_questions_not_flagged(text):
    assert not check_emergency(text).emergency


def test_build_messages_numbers_sources_and_limits_history():
    history = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    msgs = build_messages("soru", history, [Hit(CHUNK, 1.0)])
    assert msgs[0]["role"] == "system" and "[1] Grip - Belirtiler" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "soru"}
    assert len(msgs) == 1 + 12 + 1


def test_service_stream_order_and_disclaimer():
    svc = ChatService(FakeRetriever(), FakeLLM())
    events = list(svc.stream("Grip belirtileri nelerdir?"))
    assert [e["type"] for e in events] == ["sources", "token", "token", "done"]
    assert events[0]["items"][0]["url"].endswith("/Grip")
    assert DISCLAIMER in events[2]["text"]


def test_emergency_event_comes_first_and_is_not_skippable():
    llm = FakeLLM()
    svc = ChatService(FakeRetriever(), llm)
    events = list(svc.stream("nefes alamıyorum"))
    assert events[0]["type"] == "emergency" and "112" in events[0]["text"]
    assert "acil bir durum" in llm.calls[0][0]["content"]


def test_followup_is_rewritten_for_retrieval_only():
    retriever = FakeRetriever()
    svc = ChatService(retriever, FakeLLM())
    history = [{"role": "user", "content": "Grip nedir?"}, {"role": "assistant", "content": "..."}]
    out = svc.answer("Belirtileri neler?", history)
    assert retriever.queries == ["grip belirtileri"]
    assert "Grip ateşle" in out["text"] and out["sources"][0]["n"] == 1


def test_empty_answer_is_retried_then_falls_back():
    from medrag.chat.triage import EMPTY_RESPONSE

    class EmptyThenOk(FakeLLM):
        def stream(self, messages, temperature=0.3, max_tokens=1024):
            self.calls.append(messages)
            if len(self.calls) == 1:
                return iter(())
            return iter(["Grip ateşle başlar [1]."])

    llm = EmptyThenOk()
    out = ChatService(FakeRetriever(), llm, classifier=None, verifier=None).answer("Grip nedir?")
    assert len(llm.calls) == 2 and "Grip ateşle" in out["text"]

    class AlwaysEmpty(FakeLLM):
        def stream(self, messages, temperature=0.3, max_tokens=1024):
            return iter(())

    out = ChatService(FakeRetriever(), AlwaysEmpty(), classifier=None, verifier=None).answer("Grip nedir?")
    assert EMPTY_RESPONSE in out["text"]
