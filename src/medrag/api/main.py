import importlib
import json
import pkgutil
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from medrag import deps
from medrag.api import middleware
from medrag.api import routes as routes_pkg
from medrag.chat.service import ChatService

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
STATIC_DIR = WEB_DIR / "static"
PAGE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Message] = Field(default_factory=list, max_length=20)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def include_feature_routers(app: FastAPI) -> list[str]:
    """medrag.api.routes içindeki her modülün `router` nesnesini uygulamaya ekler."""
    added = []
    for info in sorted(pkgutil.iter_modules(routes_pkg.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{routes_pkg.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)
            added.append(info.name)
    return added


def create_app(service: ChatService | None = None) -> FastAPI:
    app = FastAPI(title="medrag", docs_url=None, redoc_url=None)
    if service is not None:
        app.dependency_overrides[deps.get_chat_service] = lambda: service
    middleware.install(app)

    def chat_service() -> ChatService:
        # İlk istekte yüklenir; indeks ya da anahtar yoksa hata akış içinde temiz mesaja dönüşür.
        return app.dependency_overrides.get(deps.get_chat_service, deps.get_chat_service)()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "ready": service is not None or deps.is_ready()}

    @app.post("/chat")
    @app.post("/api/chat")
    def chat(req: ChatRequest) -> StreamingResponse:
        history = [m.model_dump() for m in req.history]

        def events() -> Iterator[str]:
            try:
                for ev in chat_service().stream(req.message, history):
                    yield sse(ev)
            except Exception as e:  # noqa: BLE001 - akış ortada kopmasın, kullanıcı temiz bir hata görsün
                yield sse({"type": "error", "text": "Şu an cevap veremiyorum, lütfen biraz sonra tekrar deneyin."})
                print(f"chat hatası: {type(e).__name__}: {e}")

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    include_feature_routers(app)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # PWA dosyaları kök kapsamda sunulmalı (service worker tüm sayfaları kapsasın diye).
    root_files = {
        "sw.js": "application/javascript",
        "manifest.webmanifest": "application/manifest+json",
    }
    for name, media_type in root_files.items():

        def serve(name: str = name, media_type: str = media_type) -> FileResponse:
            path = STATIC_DIR / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path, media_type=media_type)

        app.add_api_route(f"/{name}", serve, methods=["GET"], include_in_schema=False)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/{page}", response_class=HTMLResponse)
    def page(page: str) -> str:
        path = WEB_DIR / f"{page}.html"
        if not PAGE_NAME.match(page) or not path.is_file():
            raise HTTPException(404)
        return path.read_text(encoding="utf-8")

    return app


app = create_app()
