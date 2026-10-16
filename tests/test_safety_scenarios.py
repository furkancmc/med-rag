from medrag.chat.prompt import DISCLAIMER
from medrag.eval.safety import (
    CASES,
    Case,
    InjectingRetriever,
    false_alarm_stats,
    format_report,
    run_case,
)


def answer(text, emergency=False):
    return {"text": text + "\n\n" + DISCLAIMER, "emergency": emergency, "sources_text": "[1] x"}


def judge_yes(prompt):
    return "GEREKÇE: Uygun.\nKARAR: EVET"


def test_scenario_count_and_unique_names():
    names = [c.name for c in CASES]
    assert len(CASES) >= 30 and len(set(names)) == len(names)
    assert any(c.inject for c in CASES)


def test_new_checks_and_false_alarm_rate():
    case = Case("c", "q", ["absent:HACKED", "no_emergency", "urgent", "no_diagnosis_names"])
    ok = run_case(case, answer("Hemen doktora gidin."), judge_yes)
    assert ok["passed"]
    bad = run_case(case, answer("HACKED kalp krizi", emergency=True), judge_yes)
    assert not bad["passed"] and bad["emergency"]
    calm = Case("c", "q", ["no_emergency"])
    r_bad = run_case(calm, answer("x", emergency=True), judge_yes)
    r_ok = run_case(calm, answer("x"), judge_yes)
    assert false_alarm_stats([bad, r_bad, r_ok]) == (1, 2)
    assert "Yanlış alarm oranı: 1/2" in format_report([r_bad, r_ok])


def test_injecting_retriever_puts_evil_chunk_first():
    class Inner:
        def search(self, query, k=5, mode="hybrid"):
            return [type("H", (), {"chunk": {}})() for _ in range(k)]

    hits = InjectingRetriever(Inner(), "kötü").search("x", k=3)
    assert len(hits) == 3 and hits[0].chunk["text"] == "kötü"
