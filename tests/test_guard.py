from medrag.chat.guard import NOTICE, DoseGuard, has_dose, redact_doses


def stream(pieces):
    g = DoseGuard()
    out = "".join(g.feed(p) for p in pieces)
    return out + g.flush()


def test_dose_detection_keeps_lab_values():
    assert has_dose("Günde 4000 mg alınabilir")
    assert has_dose("2 tablet ve 500 mcg, 10 damla")
    assert not has_dose("Kan şekeri 126 mg/dL üzerindeyse")
    assert not has_dose("Kolesterol 200 mg / dl")
    assert not has_dose("Tansiyon 140/90 mmHg, 2 litre su")


def test_dose_sentence_is_replaced_by_one_clean_notice():
    text = "Parasetamol ağrıyı azaltır [1]. Günde en fazla 4000 mg alınmalıdır [2]. Karaciğeri etkiler."
    out = redact_doses(text)
    assert "4000" not in out and "mg" not in out
    assert out.count(NOTICE) == 1
    assert "Parasetamol ağrıyı azaltır [1]." in out and "Karaciğeri etkiler." in out


def test_notice_is_given_only_once_per_answer():
    out = stream(["Günde 500 mg alın. ", "Ya da 2 tablet içilir. ", "Doktora danışın."])
    assert out.count(NOTICE) == 1 and "tablet" not in out and out.endswith("Doktora danışın.")


def test_number_and_unit_in_separate_stream_pieces_are_caught():
    out = stream(["Günde en fazla 40", "00", " mg", " alın.", " Doktora danışın."])
    assert "4000" not in out and NOTICE in out and out.endswith("Doktora danışın.")


def test_dose_bullet_line_is_replaced():
    out = stream(["Bilgi:\n", "- Yetişkinler 500 mg alır\n", "- Karaciğeri etkiler\n"])
    assert "500" not in out and NOTICE in out and "- Karaciğeri etkiler" in out


def test_streaming_emits_at_sentence_boundaries_and_flushes_tail():
    g = DoseGuard()
    assert g.feed("Birinci cümle") == ""
    assert g.feed(" bitti. İkin") == "Birinci cümle bitti."
    assert g.flush() == " İkin"
    assert g.flush() == ""


def test_text_without_doses_is_unchanged():
    text = "Grip ateşle başlar [1].\nİstirahat edin. Bol sıvı için."
    assert stream(list(text)) == text
