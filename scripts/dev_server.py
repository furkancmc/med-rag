"""Arayüz geliştirme sunucusu: gerçek FastAPI uygulaması + sahte servisler (ağ ve API anahtarı gerekmez).

Kullanım: python scripts/dev_server.py [--port 8765] [--access-code KOD]
  - /chat sahte akış verir; sorudaki anahtar sözcüğe göre farklı senaryolar:
      "göğüs" / "acil"   -> emergency olayı
      "doz" / "kaç mg"   -> doz reddi
      "hata"             -> error olayı
      "doğrula"          -> desteklenmeyen cümleli verification
      diğerleri          -> kaynaklı normal cevap + temiz verification
  - Aşağıdaki uç noktalar yalnızca uygulamada yoksa sahte olarak eklenir (gerçek yollar öncelikli):
      GET /api/meta/info, POST /api/feedback, POST /api/speech/transcribe
Gerçek embedding/reranker/LLM çağrısı YAPMAZ.
"""
import argparse
import os
import time
from pathlib import Path

import uvicorn
from fastapi import Request, UploadFile
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PYTHONUTF8", "1")

from medrag.api.main import create_app

DISCLAIMER = "Bu bilgiler genel bilgilendirme amaçlıdır; tıbbi tavsiye yerine geçmez. Acil durumda 112'yi arayın."

SOURCES = [
    {
        "n": 1, "title": "Diyabet", "section": "Belirtiler", "source": "MedlinePlus", "license": "Kamu malı",
        "url": "https://medlineplus.gov/diabetes.html", "published": "2024-05-10", "retrieved": "2026-10-01",
        "snippet": "Diyabetin sık görülen belirtileri aşırı susama, sık idrara çıkma ve açlık hissidir.", "text": "…",
    },
    {
        "n": 2, "title": "Şeker hastalığı", "section": "Genel bakış", "source": "Vikipedi (tr)", "license": "CC BY-SA 4.0",
        "url": "https://tr.wikipedia.org/wiki/Diyabet", "retrieved": "2026-10-01",
        "snippet": "Diyabet, kan şekerinin uzun süre yüksek seyrettiği metabolik bir hastalıktır.", "text": "…",
    },
]

NORMAL_ANSWER = (
    "Diyabetin sık görülen belirtileri şunlardır [1]:\n"
    "- Aşırı susama ve sık idrara çıkma\n"
    "- Yorgunluk ve bulanık görme\n"
    "- Yaraların geç iyileşmesi [2]\n\n"
    "Bu belirtiler başka durumlarda da görülebilir; kesin değerlendirme için hekime başvurun.\n\n"
    + DISCLAIMER
)


class FakeService:
    def stream(self, question, history):
        q = question.lower()
        time.sleep(0.25)
        if "göğüs" in q or "göğs" in q or "acil" in q:
            yield {"type": "emergency", "text": "**Bu belirtiler acil olabilir.** Lütfen beklemeden 112'yi arayın.", "reasons": ["göğüs ağrısı"]}
            yield {"type": "sources", "items": SOURCES[:1]}
            text = "Göğüs ağrısı ve kolda uyuşukluk ciddi bir durumun işareti olabilir [1]. Hemen acil servise başvurun.\n\n" + DISCLAIMER
        elif "hata" in q:
            yield {"type": "error", "text": "Şu an cevap veremiyorum, lütfen biraz sonra tekrar deneyin."}
            return
        elif "doz" in q or "kaç mg" in q:
            yield {"type": "sources", "items": SOURCES[:1]}
            text = "İlaç dozu söyleyemem; doğru doz kişiye göre değişir. Lütfen eczacınıza ya da hekiminize danışın.\n\n" + DISCLAIMER
        else:
            yield {"type": "sources", "items": SOURCES}
            text = NORMAL_ANSWER
        for i in range(0, len(text), 14):
            yield {"type": "token", "text": text[i : i + 14]}
            time.sleep(0.02)
        if "doğrula" in q:
            yield {
                "type": "verification", "checked": 4,
                "unsupported": [{"sentence": "Yaraların geç iyileşmesi", "reason": "Kaynaklarda bu ifade yok"}],
            }
        else:
            yield {"type": "verification", "checked": 4, "unsupported": []}
        yield {"type": "done"}


def build_app(access_code: str | None = None):
    app = create_app(FakeService())
    have = {getattr(r, "path", None) for r in app.routes}

    if "/api/meta/info" not in have:
        @app.get("/api/meta/info")
        def meta_info() -> dict:
            return {
                "version": "dev",
                "sources": [
                    {"source": "MedlinePlus", "license": "Kamu malı", "documents": 1200, "chunks": 9800},
                    {"source": "Vikipedi (tr)", "license": "CC BY-SA 4.0", "documents": 300, "chunks": 2500},
                ],
                "models": {"chat": "auto"},
                "eval": {"recall_at_1": 0.82, "recall_at_5": 0.96, "mrr": 0.88, "queries": 150},
            }

    if "/api/feedback" not in have:
        @app.post("/api/feedback")
        def feedback(body: dict) -> dict:
            print("geri bildirim:", {k: body.get(k) for k in ("rating", "page")})
            return {"ok": True}

    if "/api/speech/transcribe" not in have:
        @app.post("/api/speech/transcribe")
        async def transcribe(file: UploadFile) -> dict:
            await file.read()
            return {"text": "Diyabetin belirtileri nelerdir"}

    if access_code:
        @app.middleware("http")
        async def guard(request: Request, call_next):
            p = request.url.path
            protected = (p == "/chat" or p.startswith("/api/")) and p != "/api/meta/info"
            if protected and request.headers.get("x-access-code") != access_code:
                return JSONResponse({"error": "access_code_required"}, status_code=401)
            return await call_next(request)

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--access-code", default=None)
    args = ap.parse_args()
    uvicorn.run(build_app(args.access_code), host="127.0.0.1", port=args.port, log_level="warning")
