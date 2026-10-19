import re
from dataclasses import dataclass

from medrag.index.tokenize import normalize

# Her kural: (ad, regex). Metin normalize edilir (küçük harf, aksansız), kurallar da aksansız yazılır.
RULES: list[tuple[str, str]] = [
    ("kalp krizi belirtisi", (r"(gogus|gogsu|kalp)\w* .{0,40}(agri|baski|sikis|basinc|agirlik)|(agri|baski|sikis|basinc|agirlik)\w* .{0,40}(gogus|gogsu)"
        r"|agri\w* .{0,30}(kol|cene)\w* .{0,20}(yayil|vur|gid)")),
    ("felç belirtisi", r"(yuz|agiz)\w* .{0,20}(kay|carp|sark)|konus\w* .{0,25}(bozul|tutul|anlasil)|(kol|bacak|bacag)\w* .{0,20}(gucsuz|uyus|kalk)|(gucsuzluk|uyusma)\w* .{0,20}(kol|bacak|bacag)|konusma\w* bozukl|inme belirti|(kuvvet|guc) yok|yuzu\w* .{0,25}(dusmus|kaymis)|kelimeleri karistir|konusma\w* (bulanik|anlasilmiyor)|anlasilmiyor|cumle kur\w* zorlan|agzi kay"),
    ("solunum sıkıntısı", r"nefes\w* .{0,15}(alam|daral|kesil)|soluk\w* .{0,15}(alam|kesil)|nefes darlig|nefes alm\w*(iyo|iyor)|nefes almakta (cok )?zorlan|dudag\w* (mor|mosmor)|bogaz\w* kapan|hirilt|bogul"),
    ("bilinç kaybı", (r"bayil|baygin|bilinc\w* .{0,15}(kayb|kapan|bulan|yerinde degil)|kendinde degil|uyandiram"
        r"|(uyanmiyor|uyanmadi|cevap vermiyor|tepki (yok|vermiyor))|yere yigil|yigilm")),
    ("şiddetli kanama", (r"(durmayan|dinmeyen|cok fazla|siddetli|asiri) .{0,15}kanama|kan kus|(disk|kusm|kusuk|kusar)\w* .{0,25}kan|kan icinde|agzindan kan|kan (akiyor|akmaya)|kan gelmeye|ped yetmiyor|(cok|asiri) fazla kan|kanli kus|kanama\w* .{0,15}(durmuyor|dinmiyor)"
        r"|cok (fazla )?kan (kayb|gid)|kan\w* .{0,30}(durmad|durmuy|durmu |dinmed|dinmiy)|(durmad|durmuy)\w* .{0,20}kan")),
    ("zehirlenme / aşırı doz", (r"zehirlen|asiri doz|fazla (ilac|hap) (ic|al)|cok (ilac|hap) (ic|al)|(ilac|hap)\w* .{0,20}(fazla|cok) (ic|al)"
        r"|(camasir suyu|tiner|antifriz|bocek ilac|fare zehir|deterjan|temizleyici|lavabo acici|tarim ilac|gaz yag)\w*[^.]{0,30}\b(ic(ti|mis|ip)|yut\w*|yem\w*|yedi)"
        r"|(avuc|cok fazla|fazla) .{0,15}(hap|ilac|agri kesici)|(uyku )?hap\w* .{0,10}avuc|cozucu\w* (ic|yut)|(ic|yut)\w* .{0,30}bogazi yaniyor|(hap|ilac)\w* .{0,15}(sise|kutu)\w* .{0,10}bitir|(hap|ilac|tablet)\w* (yuttu|yutmus)(?!\w)|(kutu|sise)\w* .{0,25}ic(mis|ti)|pil yut|zirai ilac|sisesini agzina")),
    ("ciddi alerjik reaksiyon", r"(dil|bogaz|dudak)\w* .{0,15}(sis|kabar)|anafilaksi"),
    ("nöbet", (r"havale|nobet\w* .{0,15}(gecir|geciriyor|basla)|kasilma\w* .{0,10}(basla|var)"
        r"|nobet\w* .{0,30}(dakika|gecti)|kasil\w*, doktor|(agzi acik|tukuruk\w* akiyor).{0,40}kasil|(yerde|vucud\w*) .{0,15}kasil|gozleri (geriye|kay)|agzindan kopuk|kaskati|beden\w* sarsil|sarsilmaya basla|agzi kopur|kopuruyor|cenesi kilitlen|(dondu|sustu) .{0,40}kasil")),
    (
        "kendine zarar verme",
        (
            r"intihar|kendimi (oldur|bitir|as|kes)|yasamak istemiyor|olmek ist|olumden bahset"
        r"|kendi(m|ne|si) zarar|son vermek istiyorum|benden kurtul|yok olsam|yerim yok|bitirmek istiyorum|hic dogmasaydim|veda (eder|mesaj)|esyalarini dagit|geride birakmak|kimseye yuk|asagi bak|acimi cek|endiselenmene gerek kalmayacak|uyanmak istemiyorum|acisi cekmeyecegim|ac. cekmeyecegim|canima kiy|hayatima son|bilegimi kes|olsem daha iyi|yasamanin anlami yok"
        r"|uyuyup (hic )?uyanma|bir daha (hic )?uyanma|(hic )?uyanmasam|bensiz daha iyi"
        r"|herkes rahat eder|yok olmak istiyorum|kendimi yok|hepsini bitir|ben olmasam|kimse beni ozlemez"
        r"|herkes benden kurtulsa|varligim .{0,15}sorun|dayanacak gucum kalmadi|son kez konus|ben gidince|ilaclarini biriktir|yontem\w* (bile )?belirle"
        r"|(kac|kac tane|kac adet) .{0,30}(icersem|alirsam|yersem|yutarsam) .{0,30}(olurum|olur muyum|oldur|uyanmam)"
        ),
    ),
]
SELF_HARM_REASON = "kendine zarar verme"

COMPILED = [(name, re.compile(pattern)) for name, pattern in RULES]

EMERGENCY_MESSAGE = (
    "⚠️ Yazdıklarınız acil bir durumu işaret ediyor olabilir. Lütfen beklemeden **112 Acil Çağrı "
    "Merkezi**'ni arayın veya en yakın acil servise gidin. Mümkünse yalnız kalmayın ve yanınızda "
    "birini bulundurun."
)


SELF_HARM_RESPONSE = (
    "Bunları paylaştığınız için teşekkür ederim. Yaşadığınız şey çok ağır olabilir ve bu durumda yalnız "
    "olmak zorunda değilsiniz. Kendinize zarar verme düşünceniz varsa ya da güvende hissetmiyorsanız lütfen "
    "şimdi **112**'yi arayın veya en yakın acil servise gidin. Mümkünse güvendiğiniz bir yakınınıza ya da "
    "arkadaşınıza durumu söyleyin ve yalnız kalmayın. Bir ruh sağlığı uzmanı, bu duygularla başa çıkmanız "
    "için size destek olabilir."
)

EMPTY_RESPONSE = (
    "Şu an bu soruya cevap üretemedim. Lütfen soruyu biraz değiştirerek tekrar deneyin; "
    "sağlığınızla ilgili bir endişe varsa bir hekime danışın."
)

HARMFUL_RESPONSE = (
    "Bu isteğe yardımcı olamam. Sağlıkla ilgili güvenli bir bilgi ya da destek arıyorsanız memnuniyetle "
    "yardımcı olurum; acil bir durum varsa lütfen 112'yi arayın."
)

# Sınıflandırıcı kendine zarar dışında zararlı bir istek bulursa sistem promptuna eklenen not.
SENSITIVE_NOTE = (
    "\n\nÖNEMLİ: Kullanıcının mesajı zararlı olabilecek bir istek içeriyor. Kimseye ya da kendine zarar "
    "verecek yöntem, madde, miktar ya da talimat verme; bunu nazikçe reddet ve güvenli bir alternatif ya da "
    "bir uzmana başvurmayı öner."
)


@dataclass
class Triage:
    emergency: bool
    reasons: list[str]


# Genel bilgi / önleme sorusu: "... nasıl önlenir", "... nelerdir". Yalnızca acil olmayan kategorilerde ve
# kişisel aciliyet işareti (şimdi, hemen, yardım...) yokken acil sayılmaz; kendine zarar her zaman acildir.
INFO_RX = re.compile(
    r"onlem|onlen|risk faktor|yasam tarzi|rehabilitasyon|egitim|nedir|nelerdir|ilk yardim egitim|iletisim yontem|"
    r"aile oyku|saklama kosul|hangi \w+ tercih|kontrol\w* onerebilir"
)
URGENT_RX = re.compile(
    r"simdi|hemen|az once|su an|yardim edin|acil|yerde|dakikadir|dakika oldu|bugun|bu sabah|bayildi|nefes alam"
)


def check_emergency(text: str) -> Triage:
    norm = normalize(text)
    reasons = [name for name, rx in COMPILED if rx.search(norm)]
    if reasons and INFO_RX.search(norm) and not URGENT_RX.search(norm):
        reasons = [r for r in reasons if r.startswith(SELF_HARM_REASON)]
    return Triage(bool(reasons), reasons)


def is_self_harm(reasons: list[str]) -> bool:
    return any(r.startswith(SELF_HARM_REASON) for r in reasons)
