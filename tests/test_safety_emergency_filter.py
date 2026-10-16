import pytest

from medrag.chat.guard import (
    NOTICE,
    SAFE_EMERGENCY_SENTENCE,
    DiagnosisGuard,
    DoseGuard,
    GuardChain,
    mentions_diagnosis,
)


def run(guard, pieces):
    out = "".join(guard.feed(p) for p in pieces)
    return out + guard.flush()


@pytest.mark.parametrize("text", [
    "Göğüs ağrısı ve sol kol uyuşması, kalp krizi gibi ciddi bir durumun belirtisi olabilir.",
    "Bu belirtiler Kalp Krizi habercisi olabilir [1].",
    "Miyokard enfarktüsü acil müdahale gerektirir.",
    "Bu bir inme belirtisi olabilir.",
    "Felç riski yüksektir.",
    "Ağır alerjik reaksiyon olan anafilaksi hayatı tehdit eder.",
    "Pulmoner emboli düşünülebilir.",
    "Ateş ve ense sertliği menenjit işareti olabilir.",
    "Sepsis gelişmiş olabilir.",
    "Sağ alt karın ağrısı apandisit olabilir.",
    "İNME geçiriyor olabilirsiniz.",
])
def test_diagnosis_names_are_detected(text):
    assert mentions_diagnosis(text), text


@pytest.mark.parametrize("text", [
    "Lütfen hemen 112'yi arayın.",
    "Sakin kalın ve hareket etmeyin.",
    "Yanınızda birinin olmasını sağlayın.",
    "Göğüs ağrısı ciddi olabilir, beklemeden yardım isteyin.",
    "Merdivenlerden inmeyin, oturun.",
    "Zehirlenme şüphesi varsa ilaç kutusunu yanınızda bulundurun.",
    "Nefes almakta zorlanıyorsanız oturun.",
])
def test_action_sentences_are_not_flagged(text):
    assert not mentions_diagnosis(text), text


def test_diagnosis_sentence_is_dropped_but_actions_are_kept():
    text = (
        "Göğüs ağrısı ve sol kol uyuşması, kalp krizi gibi ciddi bir durumun belirtisi olabilir [1]. "
        "Lütfen hemen 112'yi arayın. Sakin kalın ve hareket etmeyin."
    )
    out = run(DiagnosisGuard(), list(text))
    assert "kalp krizi" not in out and "[1]" not in out
    assert out.strip() == "Lütfen hemen 112'yi arayın. Sakin kalın ve hareket etmeyin."


def test_bullet_lines_with_diagnosis_are_dropped_cleanly():
    text = "- Kalp krizi olabilir\n- 112'yi arayın\n- İnme belirtisi olabilir\n- Yalnız kalmayın\n"
    out = run(DiagnosisGuard(), [text])
    assert out == "- 112'yi arayın\n- Yalnız kalmayın\n"


def test_empty_result_gets_a_safe_sentence():
    out = run(DiagnosisGuard(), ["Bu kalp krizi olabilir. ", "Ayrıca inme belirtisi olabilir."])
    assert out.strip() == SAFE_EMERGENCY_SENTENCE
    assert "112" in out
    # hiç çıktı yokken de boş kalmaz
    assert run(DiagnosisGuard(), []) == SAFE_EMERGENCY_SENTENCE


def test_safe_sentence_is_separated_from_earlier_output():
    g = DiagnosisGuard()
    first = g.feed("Doz verilemez. ")  # bu cümle anlamlıdır, güvenli cümle gerekmez
    assert first and g.flush().strip() == ""
    g2 = DiagnosisGuard()
    g2.emitted = True  # önceden yalnızca doz açıklaması iletilmişti
    assert g2.flush().startswith(" Lütfen")


def test_only_dose_notice_left_still_gets_the_safe_sentence():
    chain = GuardChain(DoseGuard(), DiagnosisGuard())
    out = run(chain, ["Günde 500 mg alın. ", "Kalp krizi olabilir."])
    assert NOTICE in out and SAFE_EMERGENCY_SENTENCE in out and "500" not in out


def test_chain_streams_across_piece_boundaries():
    chain = GuardChain(DoseGuard(), DiagnosisGuard())
    pieces = ["112'yi ara", "yın. Kalp ", "krizi olabilir. ", "Hareket etme", "yin."]
    out = run(chain, pieces)
    assert out == "112'yi arayın. Hareket etmeyin."


def test_guards_only_emit_complete_sentences():
    g = DiagnosisGuard()
    assert g.feed("Kalp krizi") == ""  # cümle bitmeden hiçbir şey çıkmaz
    assert g.feed(" olabilir. Arayın") == ""  # tehlikeli cümle atıldı, kuyruk bekliyor
    assert g.flush().strip() == "Arayın"
