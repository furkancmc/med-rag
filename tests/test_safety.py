from medrag.chat.prompt import DISCLAIMER
from medrag.eval.safety import CASES, Case, format_report, run_case


def answer(text, emergency=False):
    return {"text": text + "\n\n" + DISCLAIMER, "emergency": emergency, "sources_text": "[1] x"}


def judge_yes(prompt):
    return "EVET\nUygun."


def judge_no(prompt):
    return "HAYIR\nTeşhis koymuş."


def test_dose_detection():
    case = Case("c", "q", ["no_dose", "referral"])
    bad = run_case(case, answer("Günde 500 mg alabilirsiniz."), judge_yes)
    assert not bad["passed"] and "500 mg" in str(bad["results"])
    good = run_case(case, answer("Doz için doktorunuza danışın."), judge_yes)
    assert good["passed"]


def test_emergency_and_112():
    case = Case("c", "q", ["emergency", "mentions_112"])
    assert run_case(case, answer("sakin olun", emergency=True), judge_yes)["passed"] is False  # 112 yok
    ok = answer("hemen 112'yi arayın", emergency=True)
    assert run_case(case, ok, judge_yes)["passed"]
    assert not run_case(case, answer("112 arayın", emergency=False), judge_yes)["passed"]


def test_judge_verdict_parsing():
    case = Case("c", "q", ["no_diagnosis"])
    assert run_case(case, answer("..."), judge_yes)["passed"]
    assert not run_case(case, answer("..."), judge_no)["passed"]


def test_missing_disclaimer_fails():
    case = Case("c", "q", [])
    assert not run_case(case, {"text": "x", "emergency": False}, judge_yes)["passed"]


def test_cases_are_wellformed_and_report_renders():
    assert len({c.name for c in CASES}) == len(CASES)
    report = format_report([run_case(Case("c", "q", ["cited"]), answer("Evet [1]"), judge_yes)])
    assert "1/1 senaryo geçti" in report
