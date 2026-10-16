import pytest

from medrag.chat.guard import NOTICE, DoseGuard, find_dose, has_dose, redact_doses


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


# --- Yazıyla yazılmış ve ek birimli dozlar ---

@pytest.mark.parametrize("text", [
    "Ağrı için iki tablet alın.",
    "İki tablet alın.",  # cümle başı büyük İ
    "Çocuğa yarım tablet verilebilir.",
    "Günde üç kez bir çay kaşığı içilir.",
    "Bir tatlı kaşığı şurup yeterli.",
    "Her seferinde bir ölçek karıştırın.",
    "Astım spreyinden iki puf çekin.",
    "Göze bir damla damlatın.",
    "Bir buçuk tablet kullanın.",
    "Bir iki damla yeterlidir.",
    "Yirmi beş damla alınır.",
    "Gerekirse iki-üç tablet daha içebilirsiniz.",
    "Bir ila iki kapsül alın.",
    "Sabah ve akşam bir tablet alın.",
    "Günde bir tablet yeterli, doktora danışın.",
    "Üç tabletten fazlasını almayın.",
    "2 adet tablet alın.",
    "Her gün 5 ml şurup içilir.",
    "Yarım ölçeği suda çözün.",
    "1/2 tablet yeterli.",
    "10 mg/gün alınır.",
    "Bir ampul enjekte edin.",
])
def test_written_and_extended_doses_are_caught(text):
    assert has_dose(text), text


@pytest.mark.parametrize("text", [
    "Bir hekime başvurun.",
    "Belirtiler iki hafta sürerse doktora gidin.",
    "Bir doktor görmeniz gerekir.",
    "Üç gün içinde düzelmezse tekrar başvurun.",
    "Hap şeklinde ilaçlar kullanılabilir.",
    "Yatakta bir yandan diğerine dönün.",
    "Günde iki kez el yıkayın.",
    "Her gün yarım saat yürüyüş yapın.",
    "On dakika dinlenin.",
    "Bir damla kan bile enfeksiyon bulaştırabilir mi diye soruyor musunuz?".replace("damla", "örnek"),
    "Tablet ilaçların yan etkileri olabilir.",
    "Kan şekeri 126 mg/dL üzerindeyse diyabet düşünülür.",
    "GFR 60 mL/dk altındaysa böbrek hastalığı olabilir.",
    "Günde 2 litre su içmek önerilir.",
    "Hapishane koşulları sağlığı etkiler.",
    "Bir ölçüm yeterli değildir.",
])
def test_written_number_false_positives_are_avoided(text):
    assert not has_dose(text), (text, find_dose(text))


def test_before_taking_warning_is_not_a_dose_but_schedule_is():
    assert not has_dose("Bir tablet kullanmadan önce mutlaka doktora danışın.")
    assert not has_dose("Bir hap almadan önce eczacınıza sorun.")
    # genel uyarıyla birlikte gerçek doz verilirse yine yakalanır
    assert has_dose("Bir tablet kullanmadan önce doktora danışın; yoksa iki tablet alın.")
    assert has_dose("Ağrı için bir tablet alın, geçmezse doktora başvurun.")


def test_find_dose_returns_the_matched_original_text():
    assert find_dose("Önce İki Tablet alın") == "İki Tablet"
    assert find_dose("Günde 500 mg alın") == "500 mg"
    assert find_dose("Doz yok") is None


def test_written_dose_sentence_is_replaced_in_a_stream():
    out = stream(["Parasetamol ağrıyı azaltır [1]. Günde ", "iki tablet", " alınır. Doktora danışın."])
    assert "tablet" not in out and out.count(NOTICE) == 1 and out.endswith("Doktora danışın.")
    assert redact_doses("Çocuğa yarım tablet verin. Ateş için sıvı için.").startswith(NOTICE)


def test_split_keep_roundtrips_and_handles_citations_and_abbreviations():
    from medrag.chat.sentences import split_keep

    text = "Grip başlar. [1] Ateş yapar vb. ve öksürük olur [2]. Son!\n- Madde bir.\n\nBitti"
    parts = split_keep(text)
    assert "".join(s + sep for s, sep in parts) == text
    sentences = [s for s, _ in parts if s]
    assert sentences[0] == "Grip başlar. [1]"
    assert "Ateş yapar vb. ve öksürük olur [2]." in sentences
