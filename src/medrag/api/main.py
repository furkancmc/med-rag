import json
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from medrag.chat.service import ChatService
from medrag.config import get_settings
from medrag.llm import EvrenLLM
from medrag.retrieve import load_retriever

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Message] = Field(default_factory=list, max_length=20)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def create_app(service: ChatService | None = None) -> FastAPI:
    app = FastAPI(title="medrag", docs_url=None, redoc_url=None)
    state = {"service": service}

    def get_service() -> ChatService:
        # İlk istekte yüklenir; indeks ve API anahtarı yoksa hata ilk /chat çağrısında görünür.
        if state["service"] is None:
            settings = get_settings()
            state["service"] = ChatService(
                load_retriever(settings),
                EvrenLLM(settings.llm_api_url, settings.llm_model),
                settings.top_k,
            )
        return state["service"]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "ready": state["service"] is not None}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    @app.post("/chat")
    def chat(req: ChatRequest) -> StreamingResponse:
        history = [m.model_dump() for m in req.history]

        def events() -> Iterator[str]:
            try:
                for ev in get_service().stream(req.message, history):
                    yield sse(ev)
            except Exception as e:  # noqa: BLE001 - akış ortada kopmasın, kullanıcı temiz bir hata görsün
                yield sse({"type": "error", "text": "Şu an cevap veremiyorum, lütfen biraz sonra tekrar deneyin."})
                print(f"chat hatası: {type(e).__name__}: {e}")

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    return app


app = create_app()
