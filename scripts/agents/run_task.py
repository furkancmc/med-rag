"""Evren API modelleriyle toplu "ajan" görevi çalıştırır (Claude Code orkestrasyonu için).

Görev dosyası (JSON):
  {"model": "glm-5.3", "system": "...", "max_tokens": 2048, "concurrency": 8,
   "extra": {"chat_template_kwargs": {"enable_thinking": false}},
   "items": [{"id": "a1", "prompt": "..."}, ...]}

Çıktı: <out> (JSONL), her satır {"id", "ok", "content" | "error"}. Mevcut satırlar atlanır (devam edilebilir).
Kullanım: python scripts/agents/run_task.py görev.json scratch/agents/ad/out.jsonl
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from medrag.config import Settings
from medrag.llm import EvrenLLM, LLMError, strip_think


def run(task: dict, out: Path, llm: EvrenLLM) -> tuple[int, int]:
    done = set()
    if out.exists():
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line]
        done = {r["id"] for r in rows if r["ok"]}  # başarısızlar yeniden denenir (en son satır geçerli)
    todo = [it for it in task["items"] if it["id"] not in done]
    system = task.get("system", "")
    client = llm.with_model(task["model"], extra_params=task.get("extra"))

    def one(item: dict) -> dict:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": item["prompt"]}
        ]
        try:
            text = client.complete(
                messages, task.get("temperature", 0.3), task.get("max_tokens", 2048)
            )
            return {"id": item["id"], "ok": True, "content": strip_think(text)}
        except LLMError as e:
            return {"id": item["id"], "ok": False, "error": str(e)}

    out.parent.mkdir(parents=True, exist_ok=True)
    ok = bad = 0
    with out.open("a", encoding="utf-8") as f, ThreadPoolExecutor(task.get("concurrency", 8)) as pool:
        for fut in as_completed([pool.submit(one, it) for it in todo]):
            row = fut.result()
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            ok, bad = ok + row["ok"], bad + (not row["ok"])
    return ok, bad


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    task = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    key = os.environ.get("EVREN_API_KEY") or dict(
        line.strip().split("=", 1) for line in Path(".env").read_text(encoding="utf-8").splitlines() if "=" in line
    ).get("EVREN_API_KEY")
    llm = EvrenLLM(Settings().embed_api_url, task["model"], api_key=key)
    ok, bad = run(task, Path(sys.argv[2]), llm)
    print(f"tamam: {ok}, hata: {bad}")


if __name__ == "__main__":
    main()
