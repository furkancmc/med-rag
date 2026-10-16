import subprocess
import sys

from fastapi import APIRouter
from fastapi.testclient import TestClient

from medrag import deps
from medrag.api.main import create_app, include_feature_routers
from medrag.config import Settings


class FakeService:
    def stream(self, question, history):
        yield {"type": "done"}


def client():
    return TestClient(create_app(FakeService()))


def test_static_assets_and_pages():
    c = client()
    assert c.get("/static/base.css").status_code == 200
    js = c.get("/static/common.js")
    assert js.status_code == 200 and "window.MedRAG" in js.text
    assert c.get("/").status_code == 200


def test_unknown_or_unsafe_pages_are_404():
    c = client()
    assert c.get("/olmayan-sayfa").status_code == 404
    assert c.get("/..%2Fconfig").status_code == 404
    assert c.get("/Index").status_code == 404


def test_chat_alias_under_api_prefix():
    c = client()
    resp = c.post("/api/chat", json={"message": "merhaba"})
    assert resp.status_code == 200 and '"done"' in resp.text


def test_feature_router_discovery(monkeypatch):
    import types

    import medrag.api.routes as routes_pkg

    fake = types.ModuleType("medrag.api.routes.zz_fake")
    fake.router = APIRouter(prefix="/api/zz")

    @fake.router.get("/ping")
    def ping():
        return {"pong": True}

    monkeypatch.setitem(sys.modules, "medrag.api.routes.zz_fake", fake)
    monkeypatch.setattr(
        "pkgutil.iter_modules",
        lambda path: [types.SimpleNamespace(name="zz_fake")],
    )
    from fastapi import FastAPI

    app = FastAPI()
    assert include_feature_routers(app) == ["zz_fake"]
    assert TestClient(app).get("/api/zz/ping").json() == {"pong": True}
    assert routes_pkg.__name__ == "medrag.api.routes"


def test_deps_are_lazy_singletons(monkeypatch):
    deps.reset()
    calls = []
    monkeypatch.setattr(
        "medrag.retrieve.load_retriever", lambda s: calls.append(s) or "retriever"
    )
    assert deps.get_retriever() == "retriever"
    assert deps.get_retriever() == "retriever"
    assert len(calls) == 1 and deps.is_ready()
    deps.reset()
    assert not deps.is_ready()


def test_settings_blocks_keep_defaults():
    s = Settings(_env_file=None)
    assert s.top_k == 5 and s.llm_model == "deepseek-v4.1-flash" and s.embed_dimensions == 1024


def test_eval_cli_discovers_subcommands():
    out = subprocess.run(
        [sys.executable, "-m", "medrag.eval", "--help"], check=True, capture_output=True, text=True
    ).stdout
    for cmd in ("gen", "run", "safety"):
        assert cmd in out
