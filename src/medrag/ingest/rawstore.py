"""Ham veri dosyaları (data/raw/<kaynak>/*.jsonl): okuma, birleştirme ve yalnız değişince yazma.

Amaç, yeniden çalıştırmanın idempotent olması: içeriği değişmeyen satır olduğu gibi (eski
`retrieved_at` değeriyle) kalır, hiçbir şey değişmediyse dosyaya hiç dokunulmaz. Böylece haftalık
yenileme yalnızca gerçekten değişen kaynaklar için git farkı üretir.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def dump_jsonl(rows: Iterable[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def write_if_changed(path: Path, text: str) -> bool:
    """Dosya içeriği aynıysa yazmaz. Yazdıysa True döner."""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


@dataclass
class MergeStats:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    kept: int = 0  # bu çalışmada getirilmeyip eski haliyle korunan satırlar
    dropped: int = 0
    written: bool = False

    def summary(self) -> str:
        return (
            f"yeni {self.added}, güncellenen {self.updated}, değişmeyen {self.unchanged}, "
            f"korunan {self.kept}, silinen {self.dropped}"
        )


Key = str | Callable[[dict], str]


def _key_fn(key: Key) -> Callable[[dict], str]:
    return key if callable(key) else (lambda row: str(row[key]))


def merge_rows(
    existing: list[dict],
    fresh: list[dict],
    key: Key,
    content_keys: tuple[str, ...],
    today: str,
    drop_old: Callable[[dict], bool] | None = None,
) -> tuple[list[dict], MergeStats]:
    """Eski ve taze satırları `key` ile birleştirir.

    - İçerik alanları (`content_keys`) aynıysa eski satır aynen korunur (retrieved_at dahil).
    - Değiştiyse ya da yeniyse taze satır `retrieved_at=today` ile yazılır.
    - Taze sette olmayan eski satırlar korunur; `drop_old(row)` True dönerse silinir.
    Çıktı `key` değerine göre sıralıdır (deterministik).
    """
    stats = MergeStats()
    kf = _key_fn(key)
    old_by_key = {kf(r): r for r in existing}
    merged: dict[str, dict] = {}
    for row in fresh:
        k = kf(row)
        old = old_by_key.get(k)
        same = old is not None and all(old.get(c) == row.get(c) for c in content_keys)
        if old is not None and same and old.get("retrieved_at"):
            merged[k] = old
            stats.unchanged += 1
        else:
            merged[k] = {**row, "retrieved_at": today}
            stats.updated += 1 if old is not None else 0
            stats.added += 0 if old is not None else 1
    for k, old in old_by_key.items():
        if k in merged:
            continue
        if drop_old and drop_old(old):
            stats.dropped += 1
        else:
            merged[k] = old
            stats.kept += 1
    return [merged[k] for k in sorted(merged)], stats


def save_merged(
    path: Path,
    fresh: list[dict],
    key: Key,
    content_keys: tuple[str, ...],
    today: str,
    drop_old: Callable[[dict], bool] | None = None,
) -> MergeStats:
    """`path` içindeki satırlarla birleştirip yalnız değişiklik varsa yazar."""
    rows, stats = merge_rows(read_jsonl(path), fresh, key, content_keys, today, drop_old)
    stats.written = write_if_changed(path, dump_jsonl(rows))
    return stats
