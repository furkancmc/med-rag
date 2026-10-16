"""İndirme için ortak ağ yardımcıları: geri çekilmeli GET, hız sınırlayıcı, paralel çalıştırıcı.

Tüm kaynak modülleri ağa `get: Callable[[str], bytes]` üzerinden erişir; testlerde sahte bir
`get` verilir, gerçek indirmede `http_get` (isteğe bağlı olarak `limited` ile sarılı) kullanılır.
"""

import json
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

USER_AGENT = "medrag/0.1 (https://github.com/furkancmc/phone; egitim amacli RAG projesi)"
MAX_BACKOFF = 120  # saniye; Retry-After bundan büyükse kırpılır

Get = Callable[[str], bytes]


def backoff_seconds(attempt: int, retry_after: str = "") -> float:
    """429/5xx sonrası bekleme: Retry-After varsa o, yoksa 5, 10, 20... sn (+ küçük rastgelelik)."""
    if retry_after.isdigit():
        return float(min(int(retry_after), MAX_BACKOFF))
    return min(5 * 2**attempt, MAX_BACKOFF) + random.uniform(0, 1)


def http_get(
    url: str,
    retries: int = 5,
    timeout: int = 60,
    headers: dict[str, str] | None = None,
) -> bytes:
    """GET isteği. 429 ve 5xx'te üstel geri çekilmeyle, ağ hatalarında kısa beklemeyle tekrar dener."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            retryable = e.code == 429 or e.code >= 500
            if not retryable or attempt == retries - 1:
                raise
            time.sleep(backoff_seconds(attempt, e.headers.get("Retry-After", "") if e.headers else ""))
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("ulaşılamaz")


class RateLimiter:
    """İş parçacıkları arasında paylaşılan hız sınırı: istekler arasında en az 1/per_second sn."""

    def __init__(
        self,
        per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.interval = 1.0 / per_second if per_second > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if not self.interval:
            return
        with self._lock:  # yer ayırma kilit altında, bekleme kilidin dışında
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            self._sleep(start - now)


def limited(get: Get, limiter: RateLimiter) -> Get:
    """`get`'i hız sınırlayıcıyla sarar."""

    def wrapped(url: str) -> bytes:
        limiter.wait()
        return get(url)

    return wrapped


def get_json(get: Get, url: str) -> Any:
    return json.loads(get(url))


def get_json_or_none(get: Get, url: str, missing: tuple[int, ...] = (404,)) -> Any | None:
    """`missing` HTTP kodlarında (varsayılan 404) None döner; diğer hatalar yükselir."""
    try:
        return json.loads(get(url))
    except urllib.error.HTTPError as e:
        if e.code in missing:
            return None
        raise


@dataclass
class Outcome:
    """Paralel çalışmada tek öğenin sonucu: ya `value` ya da `error` doludur."""

    item: Any
    value: Any = None
    error: Exception | None = None


def run_parallel(
    fn: Callable[[Any], Any],
    items: Iterable[Any],
    workers: int,
    label: str = "",
    every: int = 50,
) -> list[Outcome]:
    """`fn`'i öğeler üzerinde paralel çalıştırır; bir öğenin hatası diğerlerini durdurmaz.

    Sonuçlar girdi sırasıyla döner (deterministik çıktı için). `every` öğede bir ilerleme yazılır.
    """
    items = list(items)
    done = 0
    lock = threading.Lock()

    def one(item: Any) -> Outcome:
        nonlocal done
        try:
            out = Outcome(item, value=fn(item))
        except Exception as e:  # noqa: BLE001 - her öğenin hatası ayrı raporlanır, akış sürer
            out = Outcome(item, error=e)
        with lock:
            done += 1
            if label and every and (done % every == 0 or done == len(items)):
                print(f"{label}: {done}/{len(items)}", flush=True)
        return out

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, items))


def describe_error(e: Exception) -> str:
    """Günlükte tek satırlık hata özeti (anahtar/URL sızdırmadan sınıf ve kısa ileti)."""
    return f"{type(e).__name__}: {str(e)[:160]}"
