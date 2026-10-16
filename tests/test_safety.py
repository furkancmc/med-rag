from medrag.chat.prompt import DISCLAIMER
from medrag.eval.safety import CASES, Case, format_report, run_case


def answer(text, emergency=False):
    return {"text": text + "\n\n" + DISCLAIMER, "emergency": emergency, "sources_text": "[1] x"}


def judge_yes(prompt):
    return "GEREKÇE: Uygun.\nKARAR: EVET"


def judge_no(prompt):
    return "GEREKÇE: Teşhis koymuş.\nKARAR: HAYIR"


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


def test_judge_uses_final_verdict_and_reports_reason():
    case = Case("c", "q", ["admits_no_info"])
    ok = run_case(case, answer("..."), lambda p: "GEREKÇE: Bilgi yok dedi.\n\nKARAR: EVET")
    assert ok["passed"] and "Bilgi yok dedi" in str(ok["results"])
    assert not run_case(case, answer("..."), lambda p: "GEREKÇE: Uydurdu.\nKARAR: HAYIR")["passed"]


def test_judge_without_verdict_fails_with_explanation():
    case = Case("c", "q", ["no_diagnosis"])
    bad = run_case(case, answer("..."), lambda p: "Bilmiyorum")
    assert not bad["passed"] and "karar vermedi" in str(bad["results"])


def test_failed_report_shows_the_answer():
    bad = run_case(Case("c", "soru?", ["no_dose"]), answer("Günde 4000 mg alın."), judge_yes)
    report = format_report([bad])
    assert "Kalan senaryoların cevapları" in report and "4000 mg" in report


def test_missing_disclaimer_fails():
    case = Case("c", "q", [])
    assert not run_case(case, {"text": "x", "emergency": False}, judge_yes)["passed"]


def test_cases_are_wellformed_and_report_renders():
    assert len({c.name for c in CASES}) == len(CASES)
    report = format_report([run_case(Case("c", "q", ["cited"]), answer("Evet [1]"), judge_yes)])
    assert "1/1 senaryo geçti" in report
