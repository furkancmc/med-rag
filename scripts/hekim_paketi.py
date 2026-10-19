"""Hekim/klinik biyokimya incelemesi için tek sayfalık kontrol listesi üretir (docs/hekim-inceleme-paketi.md).

Girdi: eval/kaynaklar/med/lab_rows.json (labs/reference.py satırları) ve labs_dogrulama.jsonl (LLM doğrulama çıktısı).
Yalnızca "uyumlu" olmayan (kaynak-yok / çelişki) alanları listeler; uzmandan onay/düzeltme beklenir.
"""

import json
from pathlib import Path

D = Path("eval/kaynaklar/med")
rows = {r["id"]: r for r in json.loads((D / "lab_rows.json").read_text(encoding="utf-8"))}
checks = {}
for line in (D / "labs_dogrulama.jsonl").read_text(encoding="utf-8").splitlines():
    rec = json.loads(line)
    if rec["ok"]:
        try:
            checks[rec["id"]] = json.loads(rec["content"][rec["content"].index("{"): rec["content"].rindex("}") + 1])
        except ValueError:
            continue
lines = [
    "# Hekim inceleme paketi (tahlil referansları)", "",
    "Otomatik karşılaştırma (LLM + web kaynakları) bu aralıkları **kaynakla doğrulayamadı** ya da çelişki buldu. "
    "Lütfen her satır için: ✔ onay / ✎ düzeltme yazın. Bu liste hekim incelemesinin yerine geçmez, onu hızlandırır.", "",
    "| Test | Kayıttaki değer | Alan | Durum | Not |", "|---|---|---|---|---|",
]
n = 0
for rid, c in checks.items():
    r = rows.get(rid, {})
    ranges = r.get("ranges", {})
    val = ", ".join(f"{k}: {v[0]}–{v[1]}" for k, v in ranges.items()) + f" {r.get('unit', '')}"
    for field, label in (("range", "referans aralığı"), ("critical", "kritik eşik"), ("units", "birim çarpanı")):
        st = c.get(field, {})
        if field == "critical" and r.get("crit_low") is None and r.get("crit_high") is None:
            continue  # kritik eşik tanımlı değil: incelenecek bir şey yok
        if field == "units" and not r.get("units"):
            continue
        if st.get("status") in ("kaynak-yok", "çelişki"):
            note = st.get("note", "").replace("|", "/").replace("\n", " ")[:220]
            crit = f" kritik {r.get('crit_low')}–{r.get('crit_high')}" if field == "critical" else ""
            lines.append(f"| {r.get('name', rid)} | {val.strip()}{crit} | {label} | {st['status']} | {note} |")
            n += 1
lines += ["", f"Toplam {n} madde, {len(checks)} test."]
Path("docs/hekim-inceleme-paketi.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(n, "madde")
