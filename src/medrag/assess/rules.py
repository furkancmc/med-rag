"""Kural tabanlı kırmızı bayraklar: asgari aciliyet seviyesini belirler.

LLM kararı bu seviyenin altına asla inemez (bkz. service.final_level). Metin aksansız/küçük harfe
çevrilir; olumsuz cümleler ("ağrım yok") elenir. Sadece "olası ciddi durum" için yazılmıştır;
teşhis koymaz.
"""

import re
from dataclasses import dataclass, field

from medrag.chat.triage import check_emergency
from medrag.index.tokenize import normalize

from .models import LEVEL_ORDER, Answer, Profile

NEG = re.compile(r"\b(yok|yoktu|degil|hayir|olmadi|olmuyor|yoktur|bulunmuyor)\b")
SPLIT = re.compile(r"[.;,\n!?]|\b(?:ama|fakat|ancak|lakin)\b")
YES = re.compile(r"^(evet|var|kesinlikle|maalesef)\b")
NO = re.compile(r"^(hayir|yok|hicbiri|hic|degil|yoktur)\b")


def affirmed_clauses(text: str) -> list[str]:
    """Olumsuzluk içermeyen cümlecikleri (normalize edilmiş) döner."""
    out = []
    for part in SPLIT.split(normalize(text)):
        part = (part or "").strip()
        if part and not NEG.search(part):
            out.append(part)
    return out


@dataclass
class Context:
    strict: str  # şikâyet + serbest cevaplar (yoksayılan evet/hayır soruları hariç)
    loose: str  # strict + "evet" denilen soruların metni
    profile: Profile
    pregnant: bool = False
    months: int | None = None  # bebek yaşı (ay), biliniyorsa


@dataclass
class Flag:
    name: str
    level: str


@dataclass
class RuleResult:
    level: str = "home"
    flags: list[Flag] = field(default_factory=list)

    def add(self, name: str, level: str) -> None:
        self.flags.append(Flag(name, level))
        if LEVEL_ORDER[level] > LEVEL_ORDER[self.level]:
            self.level = level

    @property
    def reasons(self) -> list[str]:
        order = sorted(self.flags, key=lambda f: -LEVEL_ORDER[f.level])
        return [f.name for f in order]


def _rx(p: str) -> re.Pattern:
    return re.compile(p)


FEVER = _rx(r"\bates\w*|atesim|titreme")
HIGH_FEVER = _rx(r"\b(39|40|41)([.,]\d)?\s*(derece|°|c\b|santigrat)|(cok|asiri|siddetli) yuksek ates|ates\w* .{0,12}\b(39|40|41)\b|\b(39|40|41)\b .{0,8}ates")
NECK = _rx(r"ense\w* .{0,20}(sert|tutul|kasil|egil)|boyun\w* .{0,20}(sert|tutul|egil|kasil)|ense sertligi|boynumu egem")
RASH = _rx(r"dokuntu|petesi|mor leke|morarma|bastirinca (gecmeyen|solmayan)|kirmizi leke")
HEADACHE = r"(bas|kafa)\w* ?agri"
HEADACHE_RX = _rx(HEADACHE)
SUDDEN_HEADACHE = _rx(
    r"(ani|aniden|birdenbire|simsek|patlar)\w* .{0,25}" + HEADACHE
    + r"|" + HEADACHE + r"\w* .{0,30}(aniden|birdenbire|simsek|patlar|hayatimin en)"
    + r"|hayatimin en (kotu|siddetli|kuvvetli)\w* .{0,15}agri"
)
CHEST = _rx(r"(gogus|gogsum|gogs|kalp)\w* .{0,40}(agri|baski|sikis|yanma)|(agri|baski|sikis)\w* .{0,40}(gogus|gogsum)")
CHEST_RED = _rx(
    r"efor|merdiven|yuru|kosar|kosma|ter(le|im|li)|soguk ter|sol kol|kolum|kollar|cene|sirt\w* .{0,10}(yayil|vur|gec)|yayil|mide bulanti|bulanti"
)
BREATH = _rx(r"nefes\w* ?(darl|dar)|nefes alirken zorlan|soluk\w* ?(darl)|nefesim (yetmiyor|sikisiyor)")
BREATH_RED = _rx(r"istirahat|dinlenirken|konusam|cumle|dudak\w* .{0,10}(mor|morar)|morar|uykudan|yatinca|siddetli|cok ")
BLEED = _rx(r"kanama|kan geliyor|lekelen|kanli akinti|kan gelmesi")
ABD_PAIN = _rx(r"(karin|kasik)\w* ?(alti)?\w* .{0,25}(agri|kramp|sanci)|karin agri|sanci")
SEVERE = _rx(r"siddetli|dayanilmaz|cok fazla|kivran|dogrulam|sert karin")
VOMIT = _rx(r"kusma|kusuyor|kusuyorum|kustu")
DIARRHEA = _rx(r"ishal|sulu disk")
DEHYDR = _rx(r"idrar\w* .{0,15}(yok|cikmiyor|azal)|bezi islanm|bez islanm|agzi kuru|dili kuru|gozyasi yok|cok halsiz|uyusuk|emmiyor|emme")
SIGHT = _rx(r"(ani|aniden|birdenbire)\w* .{0,25}(gorme|goz)\w* .{0,15}(kayb|kapan|bulan|gormuy)|gozum (aniden )?gormuyor|bir gozumde (gorme|perde)")
CONFUSION = _rx(r"kafam (cok )?karis|zihin\w* karis|sasirik|oriyante|sacmal|kim oldugunu|nerede oldugunu")
TESTIS = _rx(r"(testis|husye|yumurta)\w* .{0,25}(ani|aniden|siddetli|sisl)|(ani|aniden|siddetli)\w* .{0,20}(testis|husye)")
HEAD_TRAUMA = _rx(r"kafa(ya|sina|mi)? .{0,15}(darbe|vur|carp|dus)|kafa travma|basimi (vur|carp)|basima .{0,10}(dustu|darbe)")
HEAD_TRAUMA_RED = _rx(r"kusma|kustu|bayil|uyku|bilinc|sersem|kulak\w* .{0,10}kan|burn\w* .{0,10}kan|nobet")
BLACK_STOOL = _rx(r"kanli (disk|gaita|kaka)|siyah (disk|gaita|kaka)|katran gibi|disk\w* .{0,15}kan\b")
BLOOD_URINE = _rx(r"kanli idrar|idrar\w* .{0,15}kan|idrarimda kan|idrar\w* .{0,10}(kirmizi|pembe|kola)")
COUGH_BLOOD = _rx(r"kan tuk|kanli balgam|oksur\w* .{0,15}kan|balgam\w* .{0,10}kan")
JAUNDICE = _rx(r"sarilik|gozlerim saril|gozlerin\w* saril|cildim saril")
FEVER_DAYS = _rx(r"ates\w* .{0,30}\b([3-9]|1\d)\s*gun|\b([3-9]|1\d)\s*gundur .{0,15}ates|(uc|dort|bes|alti|yedi|bir hafta)\w* .{0,6}gundur .{0,15}ates|ates\w* .{0,30}(uc|dort|bes|alti|yedi) gun|bir haftadir ates")
INFANT_AGE_TEXT = _rx(r"\b(\d{1,2})\s*(haftalik|gunluk)\b|yeni dogan|yenidogan|\b([0-2])\s*aylik\b")
SELF_HARM = _rx(r"kendime zarar|kendimi kes|hayatima son|yasamak istemiyorum|olmek istiyorum|intihar")
PRESSURE_HEAD_PREG = _rx(r"gorme (bulan|bozul)|gozlerimde (isik|cakma)|yuz\w* sis|el\w* sis")


def _months_from(ctx: Context) -> int | None:
    if ctx.months is not None:
        return ctx.months
    m = INFANT_AGE_TEXT.search(ctx.loose)
    if m:
        if m.group(1):
            n = int(m.group(1))
            return 0 if m.group(2) == "gunluk" else n // 4
        if m.group(3) is not None:
            return int(m.group(3))
        return 0
    return None


def evaluate_context(ctx: Context) -> RuleResult:
    res = RuleResult()
    t = ctx.loose
    p = ctx.profile
    age = p.age

    def has(rx: re.Pattern) -> bool:
        return bool(rx.search(t))


    # Mevcut sohbet kural katmanı (yalnızca şikâyet ve serbest cevaplar)
    tri = check_emergency(ctx.strict)
    for name in tri.reasons:
        res.add(f"Acil bir duruma işaret edebilen belirti: {name}", "emergency")

    fever = has(FEVER)
    months = _months_from(ctx)
    infant = (age is not None and age == 0) or months is not None
    if infant and fever:
        if months is not None and months < 3:
            res.add("3 aydan küçük bebekte ateş", "emergency")
        else:
            res.add("Bebekte ateş", "today")
    if age is not None and age < 5 and fever and has(HIGH_FEVER):
        res.add("Küçük çocukta yüksek ateş", "today")
    elif age is not None and age < 5 and fever:
        res.add("5 yaş altında ateş: hekime danışın", "soon")  # güvenli taraf: evde izlemeye bırakma
    if has(SELF_HARM):
        res.add("Kendine zarar verme düşüncesi", "emergency")
    if ctx.pregnant:
        if has(BLEED):
            res.add("Gebelikte kanama", "emergency")
        if has(ABD_PAIN):
            res.add("Gebelikte karın/kasık ağrısı", "emergency" if has(SEVERE) else "today")
        if has(HEADACHE_RX) and has(PRESSURE_HEAD_PREG):
            res.add("Gebelikte baş ağrısı ve görme/şişlik belirtisi", "today")
        if has(VOMIT) and has(_rx(r"hic (yiyem|icem)|surekli|durmuyor|hic tutmuyor")):
            res.add("Gebelikte durmayan kusma", "today")
    if has(CHEST):
        if has(CHEST_RED):
            res.add("Eforla, terlemeyle veya yayılımla birlikte göğüs ağrısı", "emergency")
        else:
            res.add("Göğüs ağrısı", "today")
    if has(BREATH):
        res.add("Nefes darlığı", "emergency" if has(BREATH_RED) else "today")
    if has(SUDDEN_HEADACHE):
        res.add("Ani başlayan çok şiddetli baş ağrısı", "emergency")
    if fever and has(NECK):
        res.add("Ateş ile birlikte ense sertliği", "emergency")
    if fever and has(RASH):
        res.add("Ateş ile birlikte döküntü/morarma", "emergency")
    if has(HIGH_FEVER) and (has(NECK) or has(RASH) or has(CONFUSION)):
        res.add("Yüksek ateş ve menenjit/sepsis uyarı belirtisi", "emergency")
    if has(SIGHT):
        res.add("Ani görme kaybı", "emergency")
    if has(CONFUSION):
        res.add("Bilinç bulanıklığı", "emergency")
    if has(TESTIS):
        res.add("Ani, şiddetli testis ağrısı", "emergency")
    if has(HEAD_TRAUMA):
        res.add("Baş travması", "emergency" if has(HEAD_TRAUMA_RED) else "today")
    if has(BLACK_STOOL):
        res.add("Dışkıda kan veya siyah dışkı", "today")
    if has(BLOOD_URINE):
        res.add("İdrarda kan", "today")
    if has(COUGH_BLOOD):
        res.add("Kanlı balgam/öksürük", "today")
    if has(JAUNDICE):
        res.add("Sarılık", "today")
    if has(HIGH_FEVER):
        res.add("Yüksek ateş", "today")
    if fever and has(FEVER_DAYS):
        res.add("3 günden uzun süren ateş", "today")
    if age is not None and age >= 65 and fever:
        res.add("İleri yaşta ateş", "today")
    if has(ABD_PAIN) and has(SEVERE):
        res.add("Şiddetli karın ağrısı", "today")
    if age is not None and age <= 5 and (has(VOMIT) or has(DIARRHEA)) and has(DEHYDR):
        res.add("Küçük çocukta kusma/ishal ve sıvı kaybı belirtisi", "today")
    if age is not None and age < 1 and (has(VOMIT) or has(DIARRHEA)):
        res.add("Bebekte kusma/ishal", "today")
    return res


def build_context(complaint: str, profile: Profile, answers: list[Answer] | None = None) -> Context:
    strict = list(affirmed_clauses(complaint))
    loose = list(strict)
    for a in answers or []:
        ans = normalize(a.answer).strip()
        if NO.match(ans):
            continue
        if YES.match(ans):
            loose.extend(affirmed_clauses(a.question))
            continue
        clauses = affirmed_clauses(a.answer)
        strict.extend(clauses)
        loose.extend(clauses)
    pregnant = bool(profile.pregnant) or any("hamile" in c or "gebe" in c for c in strict)
    return Context(" ".join(strict), " ".join(loose), profile, pregnant, profile.age_months)


def evaluate(complaint: str, profile: Profile, answers: list[Answer] | None = None) -> RuleResult:
    return evaluate_context(build_context(complaint, profile, answers))
