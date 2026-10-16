from fastapi.testclient import TestClient

from medrag.api.main import create_app
from medrag.api.routes import assess as route
from medrag.assess.jsonx import extract_json
from medrag.assess.models import Answer, FinishRequest, Profile, StartRequest
from medrag.assess.rules import evaluate
from medrag.assess.service import AssessService, parse_questions
from medrag.retrieve import Hit


class FakeRetriever:
    def search(self, query, k=5):
        chunk = {"title": "Baş ağrısı", "section": "Özet", "text": "Gerilim tipi baş ağrısı yaygındır.",
                 "url": "https://x/1", "source": "MedlinePlus", "license": "Kamu malı"}
        return [Hit(chunk, 1.0)]


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, messages, temperature=0.3, max_tokens=1024):
        self.calls += 1
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        return r


GOOD = (
    '{"level":"%s","summary":"Özet [1].","reasons":["a"],"red_flags_to_watch":["b"],'
    '"self_care":["Dinlenin.","Günde 2 tablet alın 500 mg"]}'
)


def svc(*replies):
    return AssessService(FakeRetriever(), FakeLLM(*replies))


def lvl(complaint, **profile):
    return evaluate(complaint, Profile(**profile)).level


# ---- kurallar ----
def test_rules_infant_fever_and_pregnancy():
    assert lvl("bebeğimin ateşi var", age=0, age_months=2) == "emergency"
    assert lvl("bebeğimin ateşi var", age=0) == "today"
    assert lvl("kasığımda ağrı ve kanama var", pregnant=True, sex="kadın", age=28) == "emergency"
    assert lvl("karın ağrım var", pregnant=True) == "today"
    assert lvl("karnımın alt kısmında hafif ağrı", pregnant=False, age=28) == "home"


def test_rules_chest_headache_meningitis():
    assert lvl("merdiven çıkarken göğsümde baskı ve sol koluma yayılan ağrı") == "emergency"
    assert lvl("birden gelen, hayatımın en kötü baş ağrısı") == "emergency"
    assert lvl("yüksek ateşim var ve ense sertliği hissediyorum") == "emergency"
    assert lvl("ateşim var ve vücudumda döküntü çıktı") == "emergency"
    assert lvl("nefes darlığı çekiyorum, konuşamıyorum") == "emergency"


def test_rules_mild_and_negation():
    assert lvl("hafif boğaz ağrısı ve burun akıntısı") == "home"
    assert lvl("göğüs ağrım yok ama hafif öksürüğüm var") == "home"
    assert lvl("ateşim 39 derece") == "today"


def test_rules_answers_yes_no():
    q = Answer(id="q1", question="Ense sertliği var mı?", answer="Evet")
    r = evaluate("ateşim var", Profile(), [q])
    assert r.level == "emergency"
    q2 = Answer(id="q1", question="Ense sertliği var mı?", answer="Hayır")
    assert evaluate("ateşim var", Profile(), [q2]).level == "home"


# ---- JSON ----
def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Tamam: {"a": {"b": 2}} umarım yardımcı olur') == {"a": {"b": 2}}
    assert extract_json("json yok") is None
    assert extract_json('{"a": 1') is None


def test_parse_questions_fixes_types():
    raw = ('{"questions":[{"text":"Süre?","type":"single","options":["1"]},'
           '{"text":"Şiddet?","type":"scale","options":["x"]},{"text":""},{"text":"Başka?","type":"foo"}]}')
    qs = parse_questions(raw)
    assert [q.type for q in qs] == ["text", "scale", "text"]
    assert qs[1].options is None and qs[0].id == "q1"


# ---- servis ----
def finish_req(complaint="başım ağrıyor", **kw):
    return FinishRequest(complaint=complaint, **kw)


def test_llm_cannot_lower_rule_minimum():
    s = svc(GOOD % "home")
    r = s.finish(finish_req("ateşim 39 derece"))
    assert r.level == "today" and r.self_care == []  # today için self_care yok


def test_llm_can_raise():
    r = svc(GOOD % "today").finish(finish_req())
    assert r.level == "today"
    r = svc(GOOD % "emergency").finish(finish_req())
    assert r.level == "emergency"


def test_dose_filtered_and_sources():
    r = svc(GOOD % "home").finish(finish_req())
    assert r.self_care == ["Dinlenin."]
    assert r.sources[0].n == 1 and r.sources[0].license == "Kamu malı"
    assert r.level_label == "Evde izleyebilirsiniz"


def test_repair_retry_then_success():
    s = svc("bu JSON değil", GOOD % "soon")
    r = s.finish(finish_req())
    assert r.level == "soon" and s.llm.calls == 2 and s.stats["json_repaired"] == 1


def test_unparseable_defaults_conservative():
    s = svc("saçma", "yine saçma")
    r = s.finish(finish_req())
    assert r.level == "today" and s.stats["json_failed"] == 1


def test_invalid_level_value_defaults_today():
    s = svc('{"level":"belki","summary":"x"}', '{"level":"belki","summary":"x"}')
    assert s.finish(finish_req()).level == "today"


def test_llm_error_defaults_today():
    s = svc(RuntimeError("boom"))
    assert s.finish(finish_req()).level == "today"


def test_rule_emergency_skips_llm():
    s = svc(GOOD % "home")
    r = s.finish(finish_req("birden hayatımın en kötü baş ağrısı"))
    assert r.level == "emergency" and s.llm.calls == 0


def test_start_questions_and_fallback():
    q = '{"questions":[{"id":"x","text":"Ne zamandır?","type":"single","options":["Dün","Bir hafta"]},{"text":"Şiddet?","type":"scale"},{"text":"Ateş?","type":"text"}]}'
    r = svc(q).start(StartRequest(complaint="başım ağrıyor"))
    assert not r.emergency and len(r.questions) == 3 and r.questions[0].id == "q1"
    r = svc("saçma").start(StartRequest(complaint="başım ağrıyor"))
    assert 3 <= len(r.questions) <= 5


def test_start_emergency_short_circuit():
    s = svc(GOOD % "home")
    r = s.start(StartRequest(complaint="nefes alamıyorum"))
    assert r.emergency and "112" in r.emergency_text and r.questions == [] and s.llm.calls == 0


# ---- API ----
def client(service):
    app = create_app(object())
    app.dependency_overrides[route.get_assess_service] = lambda: service
    return TestClient(app)


def test_api_validation_and_flow():
    c = client(svc('{"questions":[{"text":"a","type":"text"},{"text":"b","type":"text"},{"text":"c","type":"text"}]}', GOOD % "soon"))
    assert c.post("/api/assess/start", json={}).status_code == 422
    assert c.post("/api/assess/start", json={"complaint": "x" * 501}).status_code == 422
    assert c.post("/api/assess/start", json={"complaint": "başım ağrıyor", "sex": "diğer"}).status_code == 422
    assert c.post("/api/assess/start", json={"complaint": "başım ağrıyor", "age": -3}).status_code == 422
    ok = c.post("/api/assess/start", json={"complaint": "başım ağrıyor", "age": 30, "sex": "kadın"})
    assert ok.status_code == 200 and len(ok.json()["questions"]) == 3
    r = c.post("/api/assess/finish", json={"complaint": "başım ağrıyor", "profile": {"age": 30},
                                           "answers": [{"id": "q1", "question": "Ne zaman?", "answer": "Dün"}]})
    body = r.json()
    assert r.status_code == 200 and body["level"] == "soon" and body["disclaimer"]


def test_api_emergency_short_circuit():
    c = client(svc(GOOD % "home"))
    body = c.post("/api/assess/start", json={"complaint": "intihar etmek istiyorum"}).json()
    assert body["emergency"] is True and body["questions"] == []


def test_eval_cases_and_verdict():
    from medrag.eval.assess_cases import CASES
    from medrag.eval.assess_cli import format_report, verdict

    assert len(CASES) >= 15
    row = {"name": "x", "min": "emergency", "max": "emergency", "level": "today", "seconds": 1.0}
    assert verdict(row) == "AŞAĞI"
    assert verdict({**row, "level": "emergency"}) == "ok"
    assert verdict({**row, "min": "home", "max": "soon", "level": "today"}) == "AŞIRI"
    rows = [{**row, "verdict": "AŞAĞI"}]
    stats = {"json_calls": 2, "json_valid_first": 1, "json_repaired": 1, "json_failed": 0}
    assert "aşağı triyaj: 1" in format_report(rows, "m", stats)


def test_page_served():
    c = client(svc(GOOD % "home"))
    r = c.get("/assess")
    assert r.status_code == 200 and "app-nav" in r.text


def test_child_under_five_with_fever_is_never_home_only():
    from medrag.assess.models import Profile
    from medrag.assess.rules import evaluate

    res = evaluate("4 yaşında, iki gündür 38.2 ateş, oyun oynuyor, su içiyor.", Profile(age=4))
    assert res.level in ("soon", "today", "emergency")
    adult = evaluate("30 yaşında, bir gündür hafif ateş, genel durum iyi.", Profile(age=30))
    assert adult.level == "home"
