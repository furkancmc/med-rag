import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from medrag import deps
from medrag.api import middleware
from medrag.api.main import create_app
from medrag.api.middleware import TokenBuckets, client_ip, needs_access_code, route_class
from medrag.config import Settings
from medrag.observability import AccessLog


class FakeService:
    def stream(self, question, history):
        yield {"type": "done"}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_app(**overrides):
    settings = Settings(_env_file=None, **overrides)
    app = FastAPI()
    lines: list[str] = []
    clock = Clock()
    middleware.install(app, settings, access_log=AccessLog(sink=lines.append), clock=clock)

    @app.post("/api/chat")
    async def chat(request: Request):
        await request.body()
        return {"ok": True}

    @app.post("/api/assess/start")
    def assess():
        return {"ok": True}

    @app.post("/api/vision/medicine")
    async def vision(request: Request):
        return {"n": len(await request.body())}

    @app.get("/api/meta/info")
    def info():
        return {"public": True}

    @app.get("/api/other")
    def other():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def page():
        return {"page": True}

    return app, clock, lines


def test_token_bucket_refills_with_injected_time():
    clock = Clock()
    b = TokenBuckets(10, clock)
    assert b.take(("a",), 2, 60) == 0
    assert b.take(("a",), 2, 60) == 0
    wait = b.take(("a",), 2, 60)
    assert 0 < wait <= 1.0
    clock.t += 1.0
    assert b.take(("a",), 2, 60) == 0
    assert b.take(("b",), 2, 60) == 0  # başka anahtar bağımsız


def test_token_bucket_memory_is_bounded():
    b = TokenBuckets(3, Clock())
    for i in range(10):
        b.take((i,), 1, 1)
    assert len(b) == 3


def test_route_classes():
    assert route_class("/chat") == "chat" and route_class("/api/chat") == "chat"
    assert route_class("/api/assess/start") == "chat"
    assert route_class("/api/labs/interpret") == "chat"
    assert route_class("/api/vision/medicine") == "upload"
    assert route_class("/api/speech/transcribe") == "upload"
    assert route_class("/api/feedback") == "api"
    assert route_class("/health") is None and route_class("/static/x.js") is None


def test_rate_limit_429_with_retry_after_and_separate_budgets():
    app, clock, _ = make_app(rate_chat_burst=2, rate_chat_per_min=6, rate_api_burst=5)
    c = TestClient(app)
    assert c.post("/api/chat").status_code == 200
    assert c.post("/api/assess/start").status_code == 200  # aynı bütçe: 2. istek
    r = c.post("/api/chat")
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited" and r.json()["retry_after"] >= 1
    assert int(r.headers["retry-after"]) >= 1
    assert "content-security-policy" in r.headers  # 429'da da başlıklar var
    assert c.get("/api/other").status_code == 200  # diğer bütçe etkilenmez
    assert c.get("/health").status_code == 200
    clock.t += 20
    assert c.post("/api/chat").status_code == 200
    assert c.get("/api/meta/info").status_code == 200


def test_rate_limit_can_be_disabled():
    app, _, _ = make_app(rate_chat_burst=1, rate_limit_enabled=False)
    c = TestClient(app)
    assert all(c.post("/api/chat").status_code == 200 for _ in range(5))


def test_proxy_header_trusted_only_when_enabled():
    scope = {"client": ("1.1.1.1", 1), "headers": [(b"x-forwarded-for", b"9.9.9.9, 2.2.2.2")]}
    assert client_ip(scope, Settings(_env_file=None)) == "1.1.1.1"
    assert client_ip(scope, Settings(_env_file=None, trust_proxy_headers=True)) == "2.2.2.2"
    s2 = Settings(_env_file=None, trust_proxy_headers=True, proxy_hops=2)
    assert client_ip(scope, s2) == "9.9.9.9"


def test_rate_limit_uses_forwarded_ip_when_trusted():
    app, _, _ = make_app(rate_chat_burst=1, rate_chat_per_min=1, trust_proxy_headers=True)
    c = TestClient(app)
    assert c.post("/api/chat", headers={"X-Forwarded-For": "5.5.5.5"}).status_code == 200
    assert c.post("/api/chat", headers={"X-Forwarded-For": "5.5.5.5"}).status_code == 429
    assert c.post("/api/chat", headers={"X-Forwarded-For": "6.6.6.6"}).status_code == 200


def test_body_limits_json_and_upload():
    app, _, _ = make_app(max_json_bytes=100, max_upload_bytes=1000)
    c = TestClient(app)
    r = c.post("/api/chat", content=b"x" * 200)
    assert r.status_code == 413 and r.json()["error"] == "payload_too_large"
    assert c.post("/api/vision/medicine", content=b"x" * 500).json() == {"n": 500}
    assert c.post("/api/vision/medicine", content=b"x" * 2000).status_code == 413


def test_body_limit_enforced_on_chunked_streams():
    app, _, _ = make_app(max_json_bytes=100)
    c = TestClient(app)

    def gen():
        for _ in range(5):
            yield b"x" * 50

    assert c.post("/api/chat", content=gen()).status_code == 413


def test_security_headers_on_all_responses():
    app, _, _ = make_app(hsts=True)
    c = TestClient(app)
    for r in (c.get("/"), c.get("/yok"), c.get("/health")):
        h = r.headers
        csp = h["content-security-policy"]
        assert "connect-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "img-src 'self' data: blob:" in csp and "media-src 'self' blob:" in csp
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"]
        assert "microphone=(self)" in h["permissions-policy"] and "camera=(self)" in h["permissions-policy"]
        assert "strict-transport-security" in h
        assert h["x-request-id"]


def test_custom_csp_setting():
    app, _, _ = make_app(csp="default-src 'none'")
    assert TestClient(app).get("/").headers["content-security-policy"] == "default-src 'none'"


def test_access_code_protects_api_but_not_public_routes():
    app, _, _ = make_app(access_code="gizli")
    c = TestClient(app)
    r = c.post("/api/chat")
    assert r.status_code == 401 and r.json()["error"] == "access_code_required"
    assert c.get("/api/other", headers={"X-Access-Code": "yanlis"}).status_code == 401
    assert c.get("/api/other", headers={"X-Access-Code": "gizli"}).status_code == 200
    assert c.post("/api/chat", headers={"X-Access-Code": "gizli"}).status_code == 200
    for path in ("/", "/health", "/api/meta/info"):
        assert c.get(path).status_code == 200


def test_access_code_non_ascii_and_helper():
    app, _, _ = make_app(access_code="şifre")
    c = TestClient(app)
    assert c.get("/api/other", headers={"X-Access-Code": "şifre".encode()}).status_code == 200
    assert needs_access_code("POST", "/chat") and needs_access_code("GET", "/api/x")
    assert not needs_access_code("GET", "/api/meta/info")
    assert not needs_access_code("GET", "/sw.js") and not needs_access_code("OPTIONS", "/api/x")


def test_no_access_code_means_open():
    app, _, _ = make_app()
    assert TestClient(app).get("/api/other").status_code == 200


def test_request_id_and_access_log_has_no_sensitive_data():
    app, _, lines = make_app(access_code="gizli")
    c = TestClient(app)
    r = c.post(
        "/api/chat?q=sirdir", json={"message": "kisisel"}, headers={"X-Access-Code": "gizli"}
    )
    rec = json.loads(lines[-1])
    assert rec["request_id"] == r.headers["x-request-id"]
    assert rec["method"] == "POST" and rec["path"] == "/api/chat" and rec["status"] == 200
    text = "\n".join(lines)
    for secret in ("kisisel", "gizli", "sirdir", "testclient"):
        assert secret not in text
    assert "client" not in rec
    r = c.get("/health", headers={"X-Request-ID": "abc-12345678"})
    assert r.headers["x-request-id"] == "abc-12345678"


def test_log_client_ip_opt_in():
    settings = Settings(_env_file=None, log_client_ip=True)
    app2 = FastAPI()
    sink: list[str] = []
    middleware.install(app2, settings, access_log=AccessLog(sink=sink.append, log_client_ip=True))
    app2.get("/health")(lambda: {"ok": 1})
    TestClient(app2).get("/health")
    assert json.loads(sink[-1])["client"]


def test_metrics_recorded_and_endpoint_protected(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDRAG_ACCESS_CODE", "kod")
    monkeypatch.setenv("MEDRAG_ACCESS_LOG", "0")
    monkeypatch.setenv("MEDRAG_DATA_DIR", str(tmp_path))
    deps.reset()
    c = TestClient(create_app(FakeService()))
    c.get("/health")
    assert c.get("/api/meta/metrics").status_code == 401
    snap = c.get("/api/meta/metrics", headers={"X-Access-Code": "kod"}).json()
    assert snap["requests_total"] >= 2
    assert "GET /health" in snap["routes"]
    assert snap["status"]["4xx"] >= 1
    deps.reset()


def test_rate_limit_hits_counted():
    app, _, _ = make_app(rate_chat_burst=1, rate_chat_per_min=1)
    c = TestClient(app)
    c.post("/api/chat")
    c.post("/api/chat")
    assert app.state.metrics.snapshot()["counters"]["rate_limited.chat"] == 1


def test_streaming_sse_not_broken_by_middleware(monkeypatch):
    monkeypatch.setenv("MEDRAG_ACCESS_LOG", "0")
    deps.reset()
    c = TestClient(create_app(FakeService()))
    r = c.post("/api/chat", json={"message": "merhaba"})
    assert r.status_code == 200 and '"done"' in r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    deps.reset()


def test_warmup_loads_retriever_in_background(monkeypatch):
    calls = []
    monkeypatch.setattr("medrag.deps.get_retriever", lambda: calls.append(1))
    done = pytest.importorskip("threading").Event()
    monkeypatch.setattr("medrag.deps.get_retriever", lambda: (calls.append(1), done.set()))
    middleware._start_warmup()
    assert done.wait(2) and calls
    monkeypatch.setattr("medrag.deps.get_retriever", lambda: 1 / 0)
    middleware._start_warmup()  # hata fırlatmaz
