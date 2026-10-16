"""Sunucu ara katmanları: hız sınırı, gövde sınırı, güvenlik başlıkları, erişim kodu, istek kimliği.

Saf ASGI olarak yazıldı (akışlı SSE yanıtlarını bozmaz). `api/main.py` `install(app)` çağırır.
"""

import hmac
import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable

from fastapi import FastAPI

from medrag.config import Settings
from medrag.observability import AccessLog, Metrics

DEFAULT_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
PERMISSIONS_POLICY = "microphone=(self), camera=(self), geolocation=(), payment=()"

CHAT_PREFIXES = ("/api/assess/", "/api/labs/interpret")
CHAT_EXACT = {"/chat", "/api/chat"}
UPLOAD_PREFIXES = ("/api/vision/", "/api/speech/")
PUBLIC_API = {("GET", "/api/meta/info")}
REQUEST_ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def route_class(path: str) -> str | None:
    """Hız sınırı sınıfı: chat | upload | api; sayfa ve statik dosyalar için None."""
    if path in CHAT_EXACT or path.startswith(CHAT_PREFIXES):
        return "chat"
    if path.startswith(UPLOAD_PREFIXES):
        return "upload"
    if path.startswith("/api/"):
        return "api"
    return None


def needs_access_code(method: str, path: str) -> bool:
    if method == "OPTIONS" or (method, path) in PUBLIC_API:
        return False
    return path in CHAT_EXACT or path == "/api" or path.startswith("/api/")


class TokenBuckets:
    """Anahtar başına token bucket; en az kullanılan anahtarlar atılarak bellek sınırlanır."""

    def __init__(self, max_keys: int = 20000, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._max = max(1, max_keys)
        self._lock = threading.Lock()
        self._data: OrderedDict[tuple, tuple[float, float]] = OrderedDict()

    def take(self, key: tuple, burst: int, per_min: float) -> float:
        """Jeton alır. 0 → izin; >0 → beklenmesi gereken saniye."""
        rate = max(per_min, 0.001) / 60.0
        now = self._clock()
        with self._lock:
            tokens, last = self._data.pop(key, (float(burst), now))
            tokens = min(float(burst), tokens + (now - last) * rate)
            if tokens >= 1.0:
                tokens -= 1.0
                wait = 0.0
            else:
                wait = (1.0 - tokens) / rate
            self._data[key] = (tokens, now)
            while len(self._data) > self._max:
                self._data.popitem(last=False)
            return wait

    def __len__(self) -> int:
        return len(self._data)


class _BodyTooLarge(Exception):
    pass


def client_ip(scope, settings: Settings) -> str:
    """Gerçek istemci IP'si; vekil başlığına yalnızca ayar açıksa güvenilir."""
    if settings.trust_proxy_headers:
        wanted = settings.client_ip_header.lower().encode()
        for name, value in scope.get("headers", []):
            if name == wanted:
                parts = [p.strip() for p in value.decode("latin-1").split(",") if p.strip()]
                if parts:
                    hops = max(1, settings.proxy_hops)
                    return parts[max(0, len(parts) - hops)]
    client = scope.get("client")
    return client[0] if client else "unknown"


def _headers(scope) -> dict[bytes, bytes]:
    return {k: v for k, v in scope.get("headers", [])}


class SecurityMiddleware:
    def __init__(
        self,
        app,
        settings: Settings,
        metrics: Metrics,
        access_log: AccessLog,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.s = settings
        self.metrics = metrics
        self.log = access_log
        self.buckets = TokenBuckets(settings.rate_max_buckets, clock)
        self._clock = clock
        self._csp = (settings.csp or DEFAULT_CSP).encode("latin-1")

    # --- yardımcılar ---
    def _limits(self, cls: str) -> tuple[int, float]:
        s = self.s
        return {
            "chat": (s.rate_chat_burst, s.rate_chat_per_min),
            "upload": (s.rate_upload_burst, s.rate_upload_per_min),
            "api": (s.rate_api_burst, s.rate_api_per_min),
        }[cls]

    def _security_headers(self) -> list[tuple[bytes, bytes]]:
        out = [
            (b"content-security-policy", self._csp),
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"same-origin"),
            (b"permissions-policy", PERMISSIONS_POLICY.encode()),
            (b"x-frame-options", b"DENY"),
        ]
        if self.s.hsts:
            out.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
        return out

    def _body_limit(self, path: str) -> int:
        return self.s.max_upload_bytes if path.startswith(UPLOAD_PREFIXES) else self.s.max_json_bytes

    def _gate(self, scope) -> tuple[int, dict, dict[str, str]] | None:
        """Erişim kodu ve hız sınırı kontrolü; engelse (durum, gövde, ek başlık) döner."""
        method, path = scope["method"], scope["path"]
        cls = route_class(path)
        if cls and self.s.rate_limit_enabled and method != "OPTIONS":
            burst, per_min = self._limits(cls)
            wait = self.buckets.take((cls, client_ip(scope, self.s)), burst, per_min)
            if wait > 0:
                retry = max(1, int(wait + 0.999))
                self.metrics.incr(f"rate_limited.{cls}")
                return (
                    429,
                    {"error": "rate_limited", "retry_after": retry,
                     "message": "Çok fazla istek gönderdiniz, lütfen biraz bekleyin."},
                    {"retry-after": str(retry)},
                )
        code = self.s.access_code
        if code and needs_access_code(method, path):
            given = _headers(scope).get(b"x-access-code", b"")
            if not hmac.compare_digest(given, code.encode("utf-8")):
                self.metrics.incr("access_denied")
                return (
                    401,
                    {"error": "access_code_required", "message": "Erişim kodu gerekli."},
                    {},
                )
        return None

    # --- ASGI ---
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = self._clock()
        headers = _headers(scope)
        rid = headers.get(b"x-request-id", b"").decode("latin-1")
        if not REQUEST_ID_OK.match(rid):
            rid = uuid.uuid4().hex[:16]
        state = {"status": 500, "started": False}

        async def send_wrapped(message) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                state["started"] = True
                hdrs = list(message.get("headers", []))
                present = {k.lower() for k, _ in hdrs}
                for k, v in self._security_headers():
                    if k not in present:
                        hdrs.append((k, v))
                hdrs.append((b"x-request-id", rid.encode()))
                message = {**message, "headers": hdrs}
            await send(message)

        async def respond(status: int, body: dict, extra: dict[str, str]) -> None:
            import json

            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            hdrs = [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(data)).encode()),
            ] + [(k.encode(), v.encode()) for k, v in extra.items()]
            await send_wrapped({"type": "http.response.start", "status": status, "headers": hdrs})
            await send_wrapped({"type": "http.response.body", "body": data})

        method, path = scope["method"], scope["path"]
        try:
            blocked = self._gate(scope)
            if blocked:
                await respond(*blocked)
            else:
                limit = self._body_limit(path)
                length = headers.get(b"content-length", b"")
                if length.isdigit() and int(length) > limit:
                    self.metrics.incr("body_too_large")
                    await respond(
                        413,
                        {"error": "payload_too_large", "message": "İstek çok büyük.",
                         "limit_bytes": limit},
                        {},
                    )
                else:
                    seen = 0

                    async def receive_limited():
                        nonlocal seen
                        message = await receive()
                        if message["type"] == "http.request":
                            seen += len(message.get("body", b""))
                            if seen > limit:
                                raise _BodyTooLarge
                        return message

                    try:
                        await self.app(scope, receive_limited, send_wrapped)
                    except _BodyTooLarge:
                        self.metrics.incr("body_too_large")
                        if not state["started"]:
                            await respond(
                                413,
                                {"error": "payload_too_large", "message": "İstek çok büyük.",
                                 "limit_bytes": limit},
                                {},
                            )
        finally:
            ms = (self._clock() - start) * 1000.0
            route = scope.get("route")
            label = getattr(route, "path", None) or _fallback_label(path, state["status"])
            self.metrics.record(method, label, state["status"], ms)
            self.log.write(
                request_id=rid,
                method=method,
                path=path,
                status=state["status"],
                ms=ms,
                client=client_ip(scope, self.s) if self.s.log_client_ip else None,
            )


def _fallback_label(path: str, status: int) -> str:
    if status == 404:
        return "unmatched"
    if path.startswith("/static/"):
        return "/static/*"
    return path if len(path) <= 60 else path[:60]


def install(
    app: FastAPI,
    settings: Settings | None = None,
    *,
    access_log: AccessLog | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Ara katmanı, metrikleri ve (isteğe bağlı) ısınmayı uygulamaya bağlar."""
    settings = settings or Settings()
    metrics = Metrics()
    log = access_log or AccessLog(enabled=settings.access_log, log_client_ip=settings.log_client_ip)
    app.state.metrics = metrics
    app.state.settings = settings
    app.add_middleware(
        SecurityMiddleware, settings=settings, metrics=metrics, access_log=log, clock=clock
    )
    if settings.warmup:
        app.add_event_handler("startup", _start_warmup)


def _start_warmup() -> None:
    """İndeksi arka planda yükler; hata olursa sessizce geçer (ilk istek yeniden dener)."""

    def run() -> None:
        try:
            from medrag import deps

            deps.get_retriever()
        except Exception as e:  # noqa: BLE001 - ısınma başarısızlığı açılışı engellememeli
            print(f"ısınma atlandı: {type(e).__name__}")

    threading.Thread(target=run, name="medrag-warmup", daemon=True).start()
