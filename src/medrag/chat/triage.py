import re
from dataclasses import dataclass

from medrag.index.tokenize import normalize

# Her kural: (ad, regex). Metin normalize edilir (küçük harf, aksansız), kurallar da aksansız yazılır.
RULES: list[tuple[str, str]] = [
    ("kalp krizi belirtisi", r"(gogus|gogsum|kalp)\w* .{0,40}(agri|baski|sikis)|(agri|baski|sikis)\w* .{0,40}(gogus|gogsum)"),
    ("felç belirtisi", r"(yuz|agiz)\w* .{0,20}(kay|carp|sark)|konus\w* .{0,25}(bozul|tutul|anlasil)|(kol|bacak)\w* .{0,20}(gucsuz|uyus|kalk)"),
    ("solunum sıkıntısı", r"nefes\w* .{0,15}(alam|daral|kesil)|soluk\w* .{0,15}(alam|kesil)|bogul"),
    ("bilinç kaybı", r"bayil|bilinc\w* .{0,15}(kayb|kapan|bulan)|kendinde degil|uyandiram"),
    ("şiddetli kanama", r"(durmayan|dinmeyen|cok fazla|siddetli|asiri) .{0,15}kanama|kan kusu|kanli kus|kanama\w* .{0,15}(durmuyor|dinmiyor)"),
    ("zehirlenme / aşırı doz", r"zehirlen|asiri doz|fazla (ilac|hap) (ic|al)|cok (ilac|hap) (ic|al)|(ilac|hap)\w* .{0,20}(fazla|cok) (ic|al)"),
    ("ciddi alerjik reaksiyon", r"(dil|bogaz|dudak)\w* .{0,15}(sis|kabar)|anafilaksi"),
    ("nöbet", r"havale|nobet\w* .{0,15}(gecir|geciriyor|basla)|kasilma\w* .{0,10}(basla|var)"),
    (
        "kendine zarar verme",
        (
            r"intihar|kendimi (oldur|bitir|asmak|kes)|yasamak istemiyor|olmek istiyor"
        r"|kendime zarar|canima kiy|hayatima son|bilegimi kes|olsem daha iyi|yasamanin anlami yok"
        r"|uyuyup (hic )?uyanma|bir daha (hic )?uyanma|(hic )?uyanmasam|bensiz daha iyi"
        r"|herkes rahat eder|yok olmak istiyorum|kendimi yok|hepsini bitir|ben olmasam|kimse beni ozlemez"
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


def check_emergency(text: str) -> Triage:
    norm = normalize(text)
    reasons = [name for name, rx in COMPILED if rx.search(norm)]
    return Triage(bool(reasons), reasons)


def is_self_harm(reasons: list[str]) -> bool:
    return any(r.startswith(SELF_HARM_REASON) for r in reasons)
