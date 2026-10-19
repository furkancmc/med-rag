"""Tıbbi doğrulama görevleri: labs/reference.py satırları ve assess/rules.py iddiaları kaynak metinle karşılaştırılır."""

import json
from pathlib import Path

SRC = Path("eval/kaynaklar/med")
OUT = Path("scratch/agents/med")
OUT.mkdir(parents=True, exist_ok=True)
curated = "".join((SRC / f).read_text(encoding="utf-8") for f in ("curated.md", "curated2.md", "curated3.md"))
meritus = (SRC / "meritus_critical.txt").read_text(encoding="utf-8", errors="ignore")
uchi = (SRC / "uchicago_critical.txt").read_text(encoding="utf-8", errors="ignore")
SYSTEM = (
    "Sen titiz bir klinik doğrulama asistanısın. SADECE verilen kaynak metinlere dayan; kaynakta olmayanı "
    "uydurma. Cevabı yalnızca geçerli JSON olarak ver, başka metin yazma."
)
LAB_FMT = (
    '{"id": "...", "range": {"status": "uyumlu|çelişki|kaynak-yok", "note": "..."}, '
    '"critical": {"status": "uyumlu|çelişki|kaynak-yok", "note": "..."}, '
    '"units": {"status": "uyumlu|çelişki|kaynak-yok", "note": "..."}, '
    '"evidence": [{"claim": "...", "source_url": "...", "quote": "<kaynaktan KISA birebir alıntı>"}], '
    '"suggestion": "değişiklik gerekiyorsa somut öneri, yoksa boş"}'
)
rows = json.loads(Path("eval/kaynaklar/med/lab_rows.json").read_text(encoding="utf-8"))
items = []
for r in rows:
    page = ""
    if r["url"]:
        f = SRC / ("ml_" + r["url"].rstrip("/").split("/")[-1] + ".txt")
        if f.exists():
            page = f.read_text(encoding="utf-8")[:7000]
    prompt = (
        "Aşağıdaki tahlil kaydını (yetişkin; referans aralık, kritik eşik, birim çarpanları) kaynaklarla karşılaştır.\n"
        f"KAYIT: {json.dumps(r, ensure_ascii=False)}\n"
        "Birim çarpanı: kanonik = değer*çarpan + ofset ('units' alanı diğer_birim -> [çarpan, ofset]).\n"
        "Referans aralıkları laboratuvara göre değişir; kaynaklarda tipik aralık varsa onunla karşılaştır; "
        "kritik eşikler için kurum listelerinin aralığına bak (kurumlar arası fark normaldir: kayıt makul aralıktaysa 'uyumlu', "
        "açıkça dışındaysa 'çelişki', kaynakta hiç yoksa 'kaynak-yok').\n"
        f"Çıktı biçimi: {LAB_FMT}\n\n"
        f"=== MEDLINEPLUS SAYFASI ===\n{page}\n\n=== MERITUS KRİTİK DEĞER LİSTESİ ===\n{meritus}\n\n"
        f"=== ÜNİVERSİTE HASTANESİ KRİTİK LİSTESİ (bozuk tablo) ===\n{uchi[:2500]}\n\n=== DERLENMİŞ KANIT ===\n{curated}"
    )
    items.append({"id": r["id"], "prompt": prompt})
(OUT / "labs.json").write_text(
    json.dumps(
        {"model": "deepseek-v4.1-flash", "timeout": 420, "system": SYSTEM, "max_tokens": 8000, "concurrency": 4, "temperature": 0.1, "items": items},
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

GROUPS = {
    "ates": "3 aydan küçük bebekte ateş → emergency; bebekte (yaş 0 ya da ay biliniyor, ≥3 ay) ateş → today; 5 yaş altı yüksek ateş (≥39°C) → today; 5 yaş altı herhangi ateş → soon; ≥65 yaşta ateş → today; ateş ≥3 gün → today; yüksek ateş (≥39) tek başına → today; ateş + ense sertliği → emergency; ateş + döküntü/morarma → emergency; yüksek ateş + (ense sertliği|döküntü|konfüzyon) → emergency.",
    "gebelik": "Gebelikte kanama → emergency; gebelikte karın/kasık ağrısı → şiddetliyse emergency yoksa today; gebelikte baş ağrısı + görme bozukluğu/yüz-el şişliği → emergency; gebelikte durmayan kusma → today.",
    "gogus_solunum": "Göğüs ağrısı eforla/terleme/sol kol-çene-sırt yayılımı/bulantı ile ya da baskı/sıkışma tarifiyle → emergency, aksi halde today; nefes darlığı dinlenirken/konuşamama/dudak morarması/şiddetli ile → emergency, aksi halde today; göğüs ağrısı + nefes darlığı → emergency; ani başlayan nefes darlığı ya da morarma → emergency.",
    "norolojik": "Ani başlayan çok şiddetli (gök gürültüsü) baş ağrısı → emergency; ani görme kaybı → emergency; bilinç bulanıklığı/konfüzyon → emergency; baş travması: kusma/bayılma/uyku hali/bilinç/burun-kulaktan kan/nöbet varsa emergency, yoksa today; ani şiddetli testis ağrısı → emergency.",
    "kanama_gi": "Kanlı kusma/kahve telvesi → emergency; siyah/kanlı dışkı → today (baş dönmesi/bayılma/halsizlik ile → emergency); kanlı ishal → today; idrarda kan → today; kanlı balgam → today, nefes darlığı ile ya da çok miktarda/durmayan kanla birlikteyse emergency; sarılık → today; ateşle karın ağrısı → today; sağ alt karın ağrısı/apandisit olasılığı → today, ateş/şiddetli ağrı/kusma ile birlikteyse emergency; şiddetli karın ağrısı → today.",
    "cocuk_sivi": "5 yaş ve altı çocukta kusma/ishal + sıvı kaybı belirtisi (idrar azalması, ıslak bez yok, ağız kuruluğu, uyuşukluk) → today; 1 yaş altı bebekte kusma/ishal → today; 2 yaş ve altı çocukta yeşil (safralı) kusma → emergency.",
    "zehir_yanik_seker": "Olası zehirlenme/aşırı doz/karbonmonoksit → emergency; yanık + nefes yolu belirtisi (ses kısıklığı, is/duman, boğaz şişmesi, nefes darlığı) → emergency; kimyasal ya da elektrik yanığı → emergency; geniş/yüz-el-ayak veya 5 yaş altı çocukta yanık → today; düşük kan şekeri belirtisi → today; kendine zarar verme düşüncesi → emergency.",
}
RULE_FMT = (
    '{"group": "...", "items": [{"claim": "kuraldaki tek iddia", "code_level": "emergency|today|soon|home", '
    '"status": "uyumlu|çelişki|kaynak-yok", "recommended_level": "...", "note": "...", '
    '"evidence": [{"source_url": "...", "quote": "<KISA birebir alıntı>"}]}]}'
)
ritems = []
for gid, claims in GROUPS.items():
    ritems.append(
        {
            "id": gid,
            "prompt": (
                "Bir sağlık bilgi asistanı kural tabanlı aciliyet seviyeleri atıyor (emergency=112/acil, today=bugün hekim, "
                "soon=birkaç gün içinde randevu, home=evde izle). İlke: şüphede daha temkinli (daha yüksek) seviye. "
                "Aşağıdaki iddiaları ('KURAL') kaynak metinle karşılaştır. Seviye kaynağa göre DAHA DÜŞÜKSE 'çelişki' (tehlikeli), "
                "kaynak aynı ya da kuraldan daha düşük acillik öneriyorsa 'uyumlu' (temkinli olmak kabul), "
                "kaynak yoksa 'kaynak-yok'. Her iddiayı ayrı satır yap.\n"
                f"KURAL GRUBU '{gid}': {claims}\n\nÇıktı biçimi: {RULE_FMT}\n\n=== DERLENMİŞ KANIT ===\n{curated}"
            ),
        }
    )
(OUT / "rules.json").write_text(
    json.dumps(
        {"model": "deepseek-v4.1-flash", "timeout": 420, "system": SYSTEM, "max_tokens": 8000, "concurrency": 2, "temperature": 0.1, "items": ritems},
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
print(len(items), len(ritems))
