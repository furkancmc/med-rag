"""LLM çıktısından sağlam JSON çıkarma."""

import json
import re

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict | None:
    """Kod çitleri ve JSON öncesi/sonrası fazladan metne rağmen ilk geçerli JSON nesnesini döner."""
    if not text:
        return None
    candidates = [m.group(1) for m in FENCE.finditer(text)] + [text]
    dec = json.JSONDecoder()
    for cand in candidates:
        for m in re.finditer(r"\{", cand):
            try:
                obj, _ = dec.raw_decode(cand[m.start():])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    return None
