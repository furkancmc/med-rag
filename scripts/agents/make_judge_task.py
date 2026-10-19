"""queries_v2: üretilen soruları temizler, her soru için aday parçaları getirir ve hakem görevi hazırlar.

Girdi : scratch/agents/queries_v2/{task.json, gen.jsonl, oos.jsonl}
Çıktı : scratch/agents/queries_v2/{queries_raw.jsonl, judge.json}
Hakem her aday için "bu parça soruyu doğrudan cevaplıyor mu" der; belge düzeyinde ilgili kümeyi sonradan birleştiririz.
"""

import json
import re
import sys
from pathlib import Path

from medrag.config import Settings
from medrag.retrieve import load_retriever

D = Path("scratch/agents/queries_v2")
task = json.loads((D / "task.json").read_text(encoding="utf-8"))
meta = {it["id"]: it["meta"] for it in task["items"]}
queries = []
for line in (D / "gen.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    q = re.sub(r"^[\"'“”\s]+|[\"'“”\s]+$", "", r.get("content", "") if r["ok"] else "")
    if 8 <= len(q) <= 300 and "\n" not in q:
        queries.append({"qid": f"v2-{len(queries):04d}", "query": q, "chunk_id": r["id"], **meta[r["id"]], "oos": False})
oos_path = D / "oos.jsonl"
if oos_path.exists():
    for line in oos_path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if not r["ok"]:
            continue
        for q in r["content"].splitlines():
            q = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", q).strip()
            if 10 <= len(q) <= 200:
                queries.append({"qid": f"v2-{len(queries):04d}", "query": q, "chunk_id": None, "doc_id": None,
                                "source": "oos", "lang": "tr", "title": "", "oos": True})
print("sorular:", len(queries), "(kapsam dışı:", sum(q["oos"] for q in queries), ")", file=sys.stderr)

retr = load_retriever(Settings())
JUDGE = (
    "Bir tıbbi bilgi tabanı için arama kalitesi hakemisin. Soru ve numaralı aday parçalar verilecek. "
    "Hangi parçalar soruyu DOĞRUDAN cevaplayan bilgi içeriyor? Sadece konuya yakın olmak yetmez; cevap parçada bulunmalı. "
    "Çıktı yalnızca JSON: {{\"relevant\": [numaralar]}}. Hiçbiri cevaplamıyorsa {{\"relevant\": []}}.\n\n"
    "SORU: {q}\n\n{cands}"
)
items = []
for q in queries:
    hits = retr.search(q["query"], k=10, rerank=False, multiquery=False, mode="vector")
    bm = retr.search(q["query"], k=6, rerank=False, multiquery=False, mode="bm25")
    seen, cands = set(), []
    for h in [*hits, *bm]:
        c = h.chunk
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        cands.append(c)
    if q["chunk_id"] and q["chunk_id"] not in seen:  # üretildiği parça her zaman aday olsun (hakem doğrular)
        src = next((c for c in retr.chunks if c["id"] == q["chunk_id"]), None) if hasattr(retr, "chunks") else None
        if src:
            cands.append(src)
    q["cands"] = [{"id": c["id"], "doc_id": c["doc_id"]} for c in cands]
    text = "\n\n".join(f"[{i}] ({c['title']}) {c['text'][:700]}" for i, c in enumerate(cands))
    items.append({"id": q["qid"], "prompt": JUDGE.format(q=q["query"], cands=text)})
with (D / "queries_raw.jsonl").open("w", encoding="utf-8") as f:
    for q in queries:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")
(D / "judge.json").write_text(
    json.dumps({"model": "deepseek-v4.1-flash", "extra": {"chat_template_kwargs": {"enable_thinking": False}},
                "max_tokens": 200, "concurrency": 8, "temperature": 0.0, "items": items}, ensure_ascii=False),
    encoding="utf-8",
)
print("hakem görevi:", len(items), file=sys.stderr)
