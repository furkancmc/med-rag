"""GET /api/meta/info (herkese açık) ve GET /api/meta/metrics (erişim koduyla korunur)."""

import json
import re
import threading
from importlib import metadata
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from medrag import deps
from medrag.config import Settings

router = APIRouter(prefix="/api/meta")
_cache: dict[Path, dict] = {}
_lock = threading.Lock()


def app_version() -> str:
    try:
        return metadata.version("medrag")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def source_stats(chunks_path: Path) -> list[dict]:
    """chunks.jsonl'den kaynak başına belge/chunk sayısı; dosya yoksa boş liste. Dosya değişimine göre önbelleklenir."""
    try:
        stat = chunks_path.stat()
    except OSError:
        return []
    stamp = (stat.st_mtime_ns, stat.st_size)
    with _lock:
        hit = _cache.get(chunks_path)
        if hit and hit["stamp"] == stamp:
            return hit["value"]
    docs: dict[tuple[str, str], set] = {}
    chunks: dict[tuple[str, str], int] = {}
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            try:
                c = json.loads(line)
            except ValueError:
                continue
            key = (str(c.get("source", "?")), str(c.get("license", "")))
            docs.setdefault(key, set()).add(c.get("doc_id"))
            chunks[key] = chunks.get(key, 0) + 1
    value = [
        {"source": s, "license": lic, "documents": len(docs[(s, lic)]), "chunks": n}
        for (s, lic), n in sorted(chunks.items())
    ]
    with _lock:
        _cache[chunks_path] = {"stamp": stamp, "value": value}
    return value


def parse_eval(eval_dir: Path) -> dict:
    """eval/results.md ve safety_results.md'den kısa özet çıkarır (dosya yoksa o alan atlanır)."""
    out: dict = {}
    results = eval_dir / "results.md"
    if results.is_file():
        lines = results.read_text(encoding="utf-8").splitlines()
        info: dict = {}
        if lines and (m := re.match(r"(\d+)\s+soru", lines[0])):
            info["questions"] = int(m.group(1))
        for line in lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 6 and cells[0] == "vector":
                try:
                    info["vector"] = {
                        "recall@1": float(cells[1]),
                        "recall@5": float(cells[3]),
                        "recall@10": float(cells[4]),
                        "mrr@10": float(cells[5]),
                    }
                except ValueError:
                    pass
        if info:
            out["retrieval"] = info
    safety = eval_dir / "safety_results.md"
    if safety.is_file():
        first = safety.read_text(encoding="utf-8").splitlines()[:1]
        if first and (m := re.search(r"(\d+)/(\d+)", first[0])):
            out["safety"] = {"passed": int(m.group(1)), "total": int(m.group(2))}
    return out


@router.get("/info")
def info(settings: Annotated[Settings, Depends(deps.get_settings)]) -> dict:
    models = {
        "embedding": (
            getattr(settings, "local_embed_model", None)
            if getattr(settings, "embed_backend", "api") == "local"
            else getattr(settings, "embed_api_model", None)
        ),
        "chat": getattr(settings, "llm_model", None),
        "rerank": getattr(settings, "rerank_model", None),
        "speech": getattr(settings, "speech_model", None),
        "vision": getattr(settings, "vision_model", None),
    }
    return {
        "version": app_version(),
        "sources": source_stats(Path(settings.data_dir) / "chunks.jsonl"),
        "models": {k: v for k, v in models.items() if v},
        "eval": parse_eval(Path(settings.eval_dir)),
    }


@router.get("/metrics")
def metrics(request: Request) -> dict:
    m = getattr(request.app.state, "metrics", None)
    return m.snapshot() if m else {}
