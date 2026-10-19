import pytest

from medrag.chat.triage import check_emergency

ACIL = [
    "Babamın göğsünde sıkışma hissediyor, ağrı sol koluna yayılıyor",
    "cocugum gogsunde agri oldugunu soyluyor ve sol koluna vuruyormus acil mi",
    "Eşim aniden konuşma bozukluğu yaşıyor ve sağ bacağında güçsüzlük var",
    "Babam banyoda yere yığılmış, uyanmıyor",
    "Annem az önce kan kustu, hala devam ediyor",
    "oğlumun burnu kanıyor ve 30 dakikadır durmadı, yüzü bembeyaz oldu",
    "Annem az önce çamaşır suyu içti, ne yapmam lazım hemen!",
    "babam tiner icmis nefesi kokuyo ve sersemlemis",
    "annem tarım ilacı icmis, titriyo ve terliyo",
    "Eşim uyku haplarından bir avuç içmiş",
    "esim yerde kasiliyor yardim edin hemen",
    "Kardeşim aniden yere düştü, vücudu taş gibi kasıldı",
    "Dedem nefes darlığından konuşamıyor, yüzü soluk",
    "herkes icin daha iyi olurdu benden kurtulsalar",
    "bu dunyada yerim yok gibi, yok olsam kimse fark etmez herhalde",
    "Çocuğum arkadaşlarına veda mesajları atıyor ve eşyalarını dağıtıyor",
    "kendime zarar vermeyi düşünüyorum ve bunu durduramıyorum, artık son vermek istiyorum",
]
BILGI = [
    "Gıda zehirlenmesini önlemek için hangi saklama koşullarına dikkat edilir?",
    "Nefes darlığı yaşayan biri için hangi yaşam tarzı değişiklikleri faydalı olur?",
    "Konuşma bozukluğu olan biri için hangi iletişim yöntemleri kullanılabilir?",
    "Kol uyuşmasını önlemek için uyku pozisyonu nasıl olmalı?",
    "Anafilaksi riski taşıyan kişilerin taşıması gereken ilaçlar nelerdir?",
    "Kan bağışı nasıl yapılır?",
    "Kalp sağlığı için ne yemeliyim?",
]


@pytest.mark.parametrize("text", ACIL)
def test_acil_ifadeler_yakalanir(text):
    assert check_emergency(text).emergency


@pytest.mark.parametrize("text", BILGI)
def test_genel_bilgi_sorusu_acil_sayilmaz(text):
    assert not check_emergency(text).emergency


def test_bilgi_kalibi_kendine_zarari_bastirmaz():
    assert check_emergency("İntihar önleme hattı hangi durumlarda aranır ve nasıl çalışır?").emergency


def test_bilgi_kalibi_kisisel_aciliyette_bastirmaz():
    assert check_emergency("Zehirlenmeyi önlemek için ne yapılır? Annem şimdi çamaşır suyu içti").emergency
