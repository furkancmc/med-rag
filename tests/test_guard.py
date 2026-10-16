from medrag.chat.guard import REDACTED, DoseGuard, redact_doses


def stream(pieces):
    g = DoseGuard()
    out = "".join(g.feed(p) for p in pieces)
    return out + g.flush()


def test_redacts_doses_but_keeps_lab_values():
    assert redact_doses("Günde 4000 mg alınabilir.") == f"Günde {REDACTED} alınabilir."
    assert redact_doses("2 tablet ve 500 mcg, 10 damla") == f"{REDACTED} ve {REDACTED}, {REDACTED}"
    assert redact_doses("Kan şekeri 126 mg/dL üzerindeyse") == "Kan şekeri 126 mg/dL üzerindeyse"
    assert redact_doses("Kolesterol 200 mg / dl") == "Kolesterol 200 mg / dl"
    assert redact_doses("Tansiyon 140/90 mmHg, 2 litre su") == "Tansiyon 140/90 mmHg, 2 litre su"


def test_number_and_unit_in_separate_stream_pieces_are_caught():
    out = stream(["Günde en fazla 40", "00", " mg", " alın.", " Doktora danışın."])
    assert "4000" not in out and REDACTED in out and out.endswith("Doktora danışın.")


def test_streaming_emits_at_sentence_boundaries_and_flushes_tail():
    g = DoseGuard()
    assert g.feed("Birinci cümle") == ""
    assert g.feed(" bitti. İkin") == "Birinci cümle bitti."
    assert g.flush() == " İkin"
    assert g.flush() == ""


def test_text_without_doses_is_unchanged():
    text = "Grip ateşle başlar [1].\nİstirahat edin. Bol sıvı için."
    assert stream(list(text)) == text
