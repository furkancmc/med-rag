"""queries_v2 için soru üretim görevi: kaynak/dil dengeli parça örneklemi + üslup çeşitliliği.

Sıra: bu betik (task.json, oos.json) -> run_task.py ile gen/oos.jsonl -> make_judge_task.py -> run_task.py ile judge.out.jsonl.
Ara çıktılar scratch/agents/queries_v2 altında üretilir (repoya alınmaz); nihai set eval/queries_v2.jsonl."""

import json
import random
from collections import defaultdict
from pathlib import Path

QUOTA = {
    ("wikipedia", "tr"): 100,
    ("medlineplus", "en"): 180,
    ("wikipedia", "en"): 140,
    ("openfda", "en"): 100,
    ("europepmc", "en"): 90,
    ("cdc", "en"): 90,
}
STYLES = [
    "günlük konuşma dilinde, kısa (3-8 kelime), tıbbi terim kullanmadan, bir arkadaşa sorar gibi",
    "belirtilerini anlatan bir hasta gibi, 1-2 cümle, kişisel durum içeren (örn. 'iki gündür ...')",
    "meraklı bir kullanıcı gibi, tek cümle, hafif yazım hatası ya da küçük harf/noktalamasız yazım içeren",
    "bir yakınını soran biri gibi, tek cümle, doğal ve net",
]
PROMPT = """Aşağıdaki tıbbi metin bir bilgi tabanından alındı. Bu metinde cevabı bulunan, bir kullanıcının \
Türkçe yazabileceği TEK bir soru yaz.

Üslup: {style}.
Kurallar:
- Her zaman Türkçe yaz (metin İngilizce olsa bile).
- Metindeki cümleleri, başlığı ya da makale/ilaç adını aynen kopyalama (ilaç sorusunda ilaç adı geçebilir).
- Sadece soruyu yaz, başka hiçbir şey yazma.

Başlık: {title}
Metin: {text}"""
OUT_OF_SCOPE = (
    "Tıbbi bir bilgi tabanında CEVABI BULUNMAYAN ama sağlıkla ilgili görünen {n} farklı Türkçe kullanıcı sorusu yaz "
    "(ör. çok niş bir bitkisel kür, bir ünlünün sağlık durumu, belirli bir hastanenin randevusu, fiyat/sigorta, "
    "kişiye özel doz hesabı). Her satıra bir soru, numara ve açıklama yazma."
)

random.seed(7)
by_group = defaultdict(list)
for line in open("data/chunks.jsonl", encoding="utf-8"):
    d = json.loads(line)
    if len(d["text"].split()) >= 60 and (d["source"], d["lang"]) in QUOTA:
        by_group[(d["source"], d["lang"])].append(d)
items = []
for g, n in QUOTA.items():
    docs = {}
    for d in by_group[g]:
        docs.setdefault(d["doc_id"], d)  # belge başına tek parça: kapsama
    for i, d in enumerate(random.sample(list(docs.values()), n)):
        items.append(
            {
                "id": d["id"],
                "meta": {"doc_id": d["doc_id"], "source": d["source"], "lang": d["lang"], "title": d["title"]},
                "prompt": PROMPT.format(style=STYLES[i % len(STYLES)], title=d["title"], text=d["text"][:1800]),
            }
        )
task = {"model": "deepseek-v4.1-flash", "extra": {"chat_template_kwargs": {"enable_thinking": False}}, "max_tokens": 300, "concurrency": 12, "temperature": 0.8, "items": items}
out = Path("scratch/agents/queries_v2")
out.mkdir(parents=True, exist_ok=True)
(out / "task.json").write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
oos = {"model": "glm-5.3", "max_tokens": 1500, "items": [{"id": f"oos{i}", "prompt": OUT_OF_SCOPE.format(n=15)} for i in range(5)]}
(out / "oos.json").write_text(json.dumps(oos, ensure_ascii=False), encoding="utf-8")
print(len(items))
