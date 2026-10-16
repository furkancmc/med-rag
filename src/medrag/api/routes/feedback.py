"""Geri bildirim: POST /api/feedback (kayıt) ve GET /api/feedback/summary (özet, erişim koduyla korunur)."""

import json
import re
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from medrag import deps
from medrag.config import Settings

router = APIRouter(prefix="/api/feedback")
_lock = threading.Lock()
PAGE_OK = re.compile(r"[^a-z0-9_-]")


class FeedbackIn(BaseModel):
    rating: Literal[1, -1]
    page: str = Field(default="", max_length=40)
    question: str | None = Field(default=None, max_length=2000)
    answer: str | None = Field(default=None, max_length=6000)
    comment: str | None = Field(default=None, max_length=1000)


def feedback_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / "feedback" / "feedback.jsonl"


def rotate(path: Path, keep: int) -> None:
    """feedback.jsonl → .1 → .2 ...; en eski `keep` dosyadan fazlası silinir."""
    for i in range(keep, 0, -1):
        src = path if i == 1 else path.with_name(f"{path.name}.{i - 1}")
        dst = path.with_name(f"{path.name}.{i}")
        if src.exists():
            if i == keep and dst.exists():
                dst.unlink()
            src.replace(dst)


def append_record(settings: Settings, record: dict) -> None:
    path = feedback_path(settings)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size + len(line.encode()) > settings.feedback_max_bytes:
            rotate(path, max(1, settings.feedback_keep))
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


@router.post("")
def post_feedback(body: FeedbackIn, settings: Annotated[Settings, Depends(deps.get_settings)]) -> dict:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rating": body.rating,
        "page": PAGE_OK.sub("", body.page.lower())[:40] or "unknown",
    }
    for key in ("question", "answer", "comment"):
        value = getattr(body, key)
        if value and value.strip():
            record[key] = value.strip()
    append_record(settings, record)
    return {"ok": True}


@router.get("/summary")
def summary(settings: Annotated[Settings, Depends(deps.get_settings)]) -> dict:
    path = feedback_path(settings)
    ratings: Counter[str] = Counter()
    pages: dict[str, Counter[str]] = {}
    total = 0
    with _lock:
        files = [path] + [path.with_name(f"{path.name}.{i}") for i in range(1, 10)]
        for p in files:
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                label = "up" if rec.get("rating") == 1 else "down"
                ratings[label] += 1
                pages.setdefault(str(rec.get("page", "unknown")), Counter())[label] += 1
                total += 1
    return {
        "total": total,
        "ratings": {"up": ratings["up"], "down": ratings["down"]},
        "pages": {k: dict(v) for k, v in sorted(pages.items())},
    }
