"""Kural tabanlı acil tespitinin (chat/triage.py) yakalama ve yanlış alarm oranı: DeepSeek ile üretilmiş mesaj kümeleri.

Kümeler eval/kaynaklar/acil/set*.jsonl (satır: {"id": "acil:<kategori>" | "...normal", "content": "<JSON dizisi>"}).
set1 ve set2 kuralları ayarlarken kullanıldı; set3 ayarlamadan sonra üretilen bağımsız kümedir.
Kullanım: python scripts/acil_olcum.py eval/acil_tespit_results.md
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from medrag.chat.triage import check_emergency

lines = ["# Acil tespiti ölçümü (kural tabanlı)", "",
         "| küme | yakalama | yanlış alarm (acil olmayan) |", "|---|---|---|"]
per_cat = defaultdict(lambda: [0, 0])
misses = []
for f in sorted(Path("eval/kaynaklar/acil").glob("set*.jsonl")):
    hit = tot = fa = neg = 0
    for line in f.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        msgs = json.loads(re.search(r"\[.*\]", r["content"], re.S).group(0))
        if r["id"].endswith("normal"):
            neg += len(msgs)
            fa += sum(check_emergency(m).emergency for m in msgs)
        else:
            for m in msgs:
                e = check_emergency(m).emergency
                tot, hit = tot + 1, hit + e
                per_cat[r["id"].split(":", 1)[1]][0] += e
                per_cat[r["id"].split(":", 1)[1]][1] += 1
                if not e:
                    misses.append((f.stem, r["id"].split(":", 1)[1], m))
    lines.append(f"| {f.stem} | {hit}/{tot} (%{100 * hit / tot:.0f}) | {fa}/{neg} |")
lines += ["", "## Kategori kırılımı (tüm kümeler)", "", "| kategori | yakalama |", "|---|---|"]
lines += [f"| {c} | {h}/{n} |" for c, (h, n) in per_cat.items()]
lines += ["", f"## Kaçanlar ({len(misses)})", ""] + [f"- ({s}, {c}) {m[:200]}" for s, c, m in misses]
Path(sys.argv[1]).write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines[:12]))
