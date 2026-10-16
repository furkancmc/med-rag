import pytest

from medrag.labs.interpret import (
    convert,
    interpret_value,
    match_test,
    norm_unit,
    parse_range,
    parse_value,
)
from medrag.labs.reference import BY_ID, TESTS


def test_catalog_size_and_integrity():
    assert len(TESTS) >= 25
    assert len({t.id for t in TESTS}) == len(TESTS)
    for t in TESTS:
        assert t.url.startswith("https://medlineplus.gov/lab-tests/")
        assert t.ref_source and t.description
        for lo, hi in t.ranges.values():
            assert lo is not None or hi is not None
            if lo is not None and hi is not None:
                assert lo < hi
        if t.crit_low is not None:
            assert all(r[0] is None or t.crit_low < r[0] for r in t.ranges.values())
        if t.crit_high is not None:
            assert all(r[1] is None or t.crit_high > r[1] for r in t.ranges.values())


@pytest.mark.parametrize("name,expected", [
    ("Hemoglobin", "hemoglobin"), ("HGB", "hemoglobin"), ("hgb ", "hemoglobin"),
    ("Glukoz (Açlık)", "glucose"), ("AÇLIK KAN ŞEKERİ", "glucose"), ("Açlık Kan Şekeri", "glucose"),
    ("LDL Kolesterol", "ldl"), ("Kolesterol HDL", "hdl"), ("T. Kolesterol", "cholesterol"),
    ("Total Kolesterol", "cholesterol"), ("Trigliserid", "triglyceride"), ("TRİGLİSERİT", "triglyceride"),
    ("ALT (SGPT)", "alt"), ("SGOT", "ast"), ("Lökosit (WBC)", "wbc"), ("Üre", "urea"), ("URE", "urea"),
    ("BUN", "bun"), ("Ürik asit", "uric_acid"), ("HbA1c", "hba1c"), ("Hemoglobin A1c", "hba1c"),
    ("Serbest T4", "ft4"), ("fT4", "ft4"), ("TSH", "tsh"), ("25-OH Vitamin D", "vitamin_d"),
    ("D Vitamini", "vitamin_d"), ("Vitamin B12", "b12"), ("CRP (Kantitatif)", "crp"),
    ("Kreatinin", "creatinine"), ("Eritrosit", "rbc"), ("Sodyum", "sodium"), ("Potasyum", "potassium"),
])
def test_alias_matching(name, expected):
    assert match_test(name).id == expected


@pytest.mark.parametrize("name", ["", "   ", "Bilinmeyen test", "Direkt Bilirubin", "Kreatinin Klirensi",
                                  "Demir bağlama kapasitesi", "İdrar kreatinin"])
def test_no_false_match(name):
    assert match_test(name) is None


@pytest.mark.parametrize("raw,expected", [
    ("5,4", (5.4, "")), ("5.4", (5.4, "")), ("<0.5", (0.5, "<")), ("> 200", (200.0, ">")),
    ("≥ 10,5", (10.5, ">=")), ("1.234.567", (1234567.0, "")), ("1.234,5", (1234.5, "")),
    ("7500", (7500.0, "")), (3, (3.0, "")), (2.5, (2.5, "")),
])
def test_parse_value(raw, expected):
    assert parse_value(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "", "5-6", "5,4,3x", True])
def test_parse_value_invalid(raw):
    with pytest.raises(ValueError):
        parse_value(raw)


@pytest.mark.parametrize("raw,expected", [
    ("3.5-5.0", (3.5, 5.0)), ("0,4 - 4,0", (0.4, 4.0)), ("12.0–16.0", (12.0, 16.0)),
    ("<5", (None, 5.0)), ("< 200", (None, 200.0)), (">40", (40.0, None)), ("70 - 100 mg/dL", (70.0, 100.0)),
])
def test_parse_range(raw, expected):
    assert parse_range(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "normal", "16-12"])
def test_parse_range_none(raw):
    assert parse_range(raw) is None


def test_unit_normalization():
    assert norm_unit("10^3/µL") == norm_unit("x10³/uL") == norm_unit("10e3/ul") == norm_unit("K/uL")
    assert norm_unit("mIU/L") == norm_unit("mU/L") == "miu/l"
    assert norm_unit("%") == "pct"


def test_unit_conversions():
    glucose, chol, tg, creat = BY_ID["glucose"], BY_ID["cholesterol"], BY_ID["triglyceride"], BY_ID["creatinine"]
    assert convert(glucose, 5.5, "mmol/L") == pytest.approx(99.1, abs=0.1)
    assert convert(chol, 5.0, "mmol/L") == pytest.approx(193.35, abs=0.1)
    assert convert(tg, 1.7, "mmol/L") == pytest.approx(150.6, abs=0.1)
    assert convert(creat, 88.4, "µmol/L") == pytest.approx(1.0, abs=0.001)
    assert convert(BY_ID["wbc"], 7500, "/mm3") == pytest.approx(7.5)
    assert convert(BY_ID["hba1c"], 48, "mmol/mol") == pytest.approx(6.5, abs=0.05)
    assert convert(BY_ID["hemoglobin"], 130, "g/L") == pytest.approx(13.0)
    assert convert(BY_ID["hematocrit"], 0.42, "L/L") == pytest.approx(42.0)
    assert convert(BY_ID["crp"], 0.5, "mg/dL") == pytest.approx(5.0)
    assert convert(glucose, 5, "bilinmeyen") is None
    assert convert(glucose, 5, None) is None  # birim yok, birden çok seçenek: tahmin yok


def test_classification_basic():
    assert interpret_value("Glukoz", "92", "mg/dL").status == "normal"
    assert interpret_value("Glukoz", "108", "mg/dL").status == "high"
    assert interpret_value("Glukoz", "62", "mg/dL").status == "low"
    assert interpret_value("Glukoz", "5,4", "mmol/L").status == "normal"  # 97,3 mg/dL
    assert interpret_value("Glukoz", "6,5", "mmol/L").status == "high"
    r = interpret_value("HDL", "35", "mg/dL", sex="male")
    assert r.status == "low" and r.range["high"] is None


def test_sex_specific():
    assert interpret_value("Hemoglobin", "12.5", "g/dL", sex="female").status == "normal"
    assert interpret_value("Hemoglobin", "12.5", "g/dL", sex="male").status == "low"
    assert interpret_value("Ferritin", "20", "ng/mL", sex="female").status == "normal"
    assert interpret_value("Kreatinin", "1.2", "mg/dL", sex="female").status == "high"
    assert interpret_value("Kreatinin", "1.2", "mg/dL", sex="male").status == "normal"


def test_missing_sex_uses_broad_range_with_note():
    r = interpret_value("Hemoglobin", "13.0", "g/dL")
    assert r.status == "normal" and "geniş aralık" in r.note
    assert r.range["low"] == 12.1 and r.range["high"] == 17.2
    # geniş aralığın dışı yine de işaretlenir
    assert interpret_value("Hemoglobin", "11.0", "g/dL").status == "low"


def test_critical_values():
    r = interpret_value("Potasyum", "6.9", "mmol/L")
    assert r.status == "critical" and r.direction == "high" and "Kritik" in r.note
    assert interpret_value("Sodyum", "118", "mmol/L").direction == "low"
    r = interpret_value("Glukoz", "35", "mg/dL")
    assert r.status == "critical" and r.direction == "low"
    r = interpret_value("Hemoglobin", "6.5", "g/dL", sex="female")
    assert r.status == "critical"
    # kullanıcı aralığı vermiş olsa bile kritik eşik geçerli
    assert interpret_value("Potasyum", "7.0", "mmol/L", ref_low=3.5, ref_high=8.0).status == "critical"
    # kritik eşik mmol/L girişte de çalışır
    assert interpret_value("Glukoz", "1.8", "mmol/L").status == "critical"


def test_user_range_overrides():
    # Kendi aralığı 70-110 olan raporda 105 normal; yerleşik aralıkta yüksek
    assert interpret_value("Glukoz", "105", "mg/dL").status == "high"
    r = interpret_value("Glukoz", "105", "mg/dL", ref_low=70, ref_high=110)
    assert r.status == "normal" and r.range["source"].startswith("Rapor")
    r = interpret_value("TSH", "5,0", "mIU/L", ref_low="0,4", ref_high="5,5")
    assert r.status == "normal"
    # birimi farklı girilen kullanıcı aralığı girilen birimde değerlendirilir
    assert interpret_value("Glukoz", "6.0", "mmol/L", ref_low=3.9, ref_high=5.6).status == "high"


def test_unknown_unit_never_guessed():
    r = interpret_value("Glukoz", "108", "xyz")
    assert r.status == "unknown" and "tanınmadı" in r.note
    r = interpret_value("Glukoz", "5.4", None)
    assert r.status == "unknown" and "birim" in r.note.lower()
    # tek birimli testte birim yoksa kanonik varsayılır
    assert interpret_value("MCV", "90", None).status == "normal"


def test_unknown_test_and_bad_value():
    r = interpret_value("Bilinmeyen", "5", "mg/dL")
    assert r.status == "unknown" and r.test_id is None
    r = interpret_value("Glukoz", "çok", "mg/dL")
    assert r.status == "unknown" and r.value is None
    assert interpret_value("Glukoz", "-5", "mg/dL").status == "unknown"


def test_qualified_values():
    assert interpret_value("CRP", "<0.5", "mg/L").status == "unknown"  # alt sınır yok: <0.5 kesin normal sayılmaz
    assert interpret_value("Ferritin", "<5", "ng/mL", sex="female").status == "low"
    assert interpret_value("CRP", ">200", "mg/L").status == "high"
    assert interpret_value("Glukoz", ">60", "mg/dL").status == "unknown"


def test_hba1c_and_age_note():
    assert interpret_value("HbA1c", "6.8", "%").status == "high"
    assert interpret_value("HbA1c", "42", "mmol/mol").status == "high"  # 6,0 %
    assert "çocuk" in interpret_value("TSH", "2", "mIU/L", age=10).note
    r = interpret_value("Üre", "30", "mg/dL")
    assert r.status == "normal"


def test_wbc_display_range_in_input_unit():
    r = interpret_value("WBC", "7500", "/mm3")
    assert r.status == "normal"
    assert r.range["low"] == 4500 and r.range["high"] == 11000 and r.range["unit"] == "/mm3"
