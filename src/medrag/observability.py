"""Gözlemlenebilirlik: bellek içi metrikler ve yapılandırılmış (JSON) erişim logu.

Kişisel veri yazılmaz: gövde, başlık ve sorgu parametresi loglanmaz; IP yalnızca ayar açıksa yazılır.
Metrikler süreç belleğindedir (çok işçili çalışmada her işçi kendi sayaçlarını tutar).
"""

import json
import logging
import sys
import threading
import time
from collections import Counter, deque
from collections.abc import Callable

MAX_ROUTE_KEYS = 200  # etiket sayısı sınırı (bellek ve çıktı boyutu)
LATENCY_WINDOW = 1000  # her rota için son N gecikme


def percentile(sorted_values: list[float], q: float) -> float:
    """En yakın sıra (nearest-rank) yüzdeliği; liste boşsa 0."""
    if not sorted_values:
        return 0.0
    rank = max(1, int(-(-q * len(sorted_values) // 100)))  # tavan
    return sorted_values[min(rank, len(sorted_values)) - 1]


def status_class(status: int) -> str:
    return f"{status // 100}xx"


class Metrics:
    """İş parçacığı güvenli sayaçlar: rota başına istek sayısı, durum sınıfı ve gecikme yüzdelikleri."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started = clock()
        self._lock = threading.Lock()
        self._routes: dict[str, dict] = {}
        self._status: Counter[str] = Counter()
        self._counters: Counter[str] = Counter()
        self._total = 0

    def record(self, method: str, route: str, status: int, ms: float) -> None:
        """Bir isteğin sonucunu kaydeder. `route` şablon olmalı (ham yol değil)."""
        key = f"{method} {route}"
        with self._lock:
            entry = self._routes.get(key)
            if entry is None:
                if len(self._routes) >= MAX_ROUTE_KEYS:
                    key = "other"
                    entry = self._routes.get(key)
                if entry is None:
                    entry = {
                        "count": 0,
                        "status": Counter(),
                        "latency": deque(maxlen=LATENCY_WINDOW),
                        "sum_ms": 0.0,
                        "max_ms": 0.0,
                    }
                    self._routes[key] = entry
            entry["count"] += 1
            entry["status"][status_class(status)] += 1
            entry["latency"].append(ms)
            entry["sum_ms"] += ms
            entry["max_ms"] = max(entry["max_ms"], ms)
            self._status[status_class(status)] += 1
            self._total += 1

    def incr(self, name: str, n: int = 1) -> None:
        """Serbest sayaç (ör. `rate_limited.chat`, `speech.ok`)."""
        with self._lock:
            self._counters[name] += n

    def snapshot(self) -> dict:
        with self._lock:
            routes = {}
            for key, e in sorted(self._routes.items()):
                values = sorted(e["latency"])
                routes[key] = {
                    "count": e["count"],
                    "status": dict(sorted(e["status"].items())),
                    "latency_ms": {
                        "avg": round(e["sum_ms"] / e["count"], 1) if e["count"] else 0.0,
                        "p50": round(percentile(values, 50), 1),
                        "p95": round(percentile(values, 95), 1),
                        "p99": round(percentile(values, 99), 1),
                        "max": round(e["max_ms"], 1),
                    },
                }
            return {
                "uptime_s": round(self._clock() - self._started, 1),
                "requests_total": self._total,
                "status": dict(sorted(self._status.items())),
                "counters": dict(sorted(self._counters.items())),
                "routes": routes,
            }


def json_line(**fields) -> str:
    return json.dumps(fields, ensure_ascii=False, separators=(",", ":"))


class AccessLog:
    """Her istek için tek satırlık JSON log. `sink` testlerde değiştirilebilir."""

    def __init__(
        self,
        sink: Callable[[str], None] | None = None,
        enabled: bool = True,
        log_client_ip: bool = False,
    ) -> None:
        self.enabled = enabled
        self.log_client_ip = log_client_ip
        self._sink = sink or default_sink()

    def write(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status: int,
        ms: float,
        client: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        fields = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
            "level": "info",
            "msg": "request",
            "request_id": request_id,
            "method": method,
            "path": path[:200],
            "status": status,
            "ms": round(ms, 1),
        }
        if self.log_client_ip and client:
            fields["client"] = client
        try:
            self._sink(json_line(**fields))
        except Exception:  # noqa: BLE001 - log yazılamaması isteği asla bozmasın
            return


_logger = logging.getLogger("medrag.access")


def default_sink() -> Callable[[str], None]:
    """`medrag.access` logger'ına yazar; işleyici yoksa stdout'a düz mesaj olarak basar."""
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
        _logger.propagate = False
    return _logger.info
