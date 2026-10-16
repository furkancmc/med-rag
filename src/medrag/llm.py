import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    pass


THINK_CLOSED = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
MAX_TOKENS_CAP = 8192  # "length" ile kesilen boş cevaplarda max_tokens en fazla buraya kadar artırılır


def strip_think(text: str) -> str:
    """Satır içi <think>...</think> bloklarını atar (bazı düşünen modeller bunu içeriğe yazar)."""
    text = THINK_CLOSED.sub("", text)
    low = text.lower()
    if "</think>" in low:  # açılış etiketi şablonda kalmış olabilir: kapanıştan sonrası cevaptır
        text = text[low.rfind("</think>") + len("</think>") :]
    low = text.lower()
    if "<think>" in low:  # kapanmamış düşünme: cevap henüz başlamamış
        text = text[: low.find("<think>")]
    return text.strip()


class ThinkStripper:
    """Akan metinden <think>...</think> bloklarını ayıklar (etiket iki parçaya bölünse bile)."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.inside = False
        self.buffer = ""

    def feed(self, piece: str) -> str:
        self.buffer += piece
        out: list[str] = []
        while self.buffer:
            tag = self.CLOSE if self.inside else self.OPEN
            idx = self.buffer.lower().find(tag)
            if idx >= 0:
                if not self.inside:
                    out.append(self.buffer[:idx])
                self.buffer = self.buffer[idx + len(tag) :]
                self.inside = not self.inside
                continue
            keep = 0  # sonda etiketin başlangıcı olabilecek kısmı beklet
            for n in range(min(len(tag) - 1, len(self.buffer)), 0, -1):
                if tag.startswith(self.buffer[-n:].lower()):
                    keep = n
                    break
            emit, self.buffer = self.buffer[: len(self.buffer) - keep], self.buffer[len(self.buffer) - keep :]
            if not self.inside:
                out.append(emit)
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self.buffer = self.buffer, ""
        return "" if self.inside else rest


def sse_parts(line: str) -> tuple[str | None, str | None]:
    """Bir SSE satırından (içerik, akıl yürütme) metin parçalarını çıkarır."""
    line = line.strip()
    if not line.startswith("data:"):
        return None, None
    body = line[5:].strip()
    if not body or body == "[DONE]":
        return None, None
    try:
        choices = json.loads(body).get("choices") or []  # son parça (usage) 'choices' boş gelebilir
    except (ValueError, AttributeError):
        return None, None
    if not choices:
        return None, None
    delta = choices[0].get("delta") or {}
    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
    return delta.get("content") or None, reasoning or None


def sse_delta(line: str) -> str | None:
    """Bir SSE satırından metin parçasını çıkarır; ilgisiz satır, [DONE] ve boş 'choices' için None."""
    return sse_parts(line)[0]


def parse_extra_params(text: str | None) -> dict:
    """`MEDRAG_*_EXTRA_PARAMS` ayarını (JSON nesnesi) sözlüğe çevirir; boşsa {} döner."""
    if not text or not text.strip():
        return {}
    try:
        value = json.loads(text)
    except ValueError as e:
        raise ValueError(f"ek istek parametreleri geçerli JSON değil: {e}") from e
    if not isinstance(value, dict):
        raise TypeError("ek istek parametreleri bir JSON nesnesi olmalı")
    return value


def _content_text(content: Any) -> str:
    """OpenAI 'content' alanı düz metin ya da parça listesi olabilir."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


@dataclass
class Completion:
    """Tek bir /chat/completions cevabının ayrıştırılmış hali (teşhis için ham veriyi de taşır)."""

    content: str  # <think> blokları atılmış, boş olabilir
    reasoning: str = ""  # modelin 'reasoning' / 'reasoning_content' alanı
    finish_reason: str | None = None
    model: str | None = None
    usage: dict = field(default_factory=dict)
    refusal: str | None = None

    def describe(self) -> str:
        return (
            f"finish_reason={self.finish_reason}, refusal={self.refusal!r}, model={self.model}, "
            f"reasoning_chars={len(self.reasoning)}"
        )


def parse_completion(data: dict) -> Completion:
    try:
        choice = data["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Beklenmeyen LLM cevabı: {str(data)[:200]}") from e
    usage = data.get("usage") or {}
    routed = (usage.get("evren") or {}).get("routed_model") if isinstance(usage, dict) else None
    return Completion(
        content=strip_think(_content_text(message.get("content"))),
        reasoning=_content_text(message.get("reasoning_content") or message.get("reasoning")).strip(),
        finish_reason=choice.get("finish_reason"),
        model=routed or data.get("model"),
        usage=usage if isinstance(usage, dict) else {},
        refusal=message.get("refusal"),
    )


def _retry_after(e: urllib.error.HTTPError) -> float | None:
    try:
        value = float((e.headers or {}).get("Retry-After", ""))
    except (TypeError, ValueError):
        return None
    return min(max(value, 0.0), 60.0)


class EvrenLLM:
    """OpenAI uyumlu /chat/completions istemcisi (Evren API). Anahtar EVREN_API_KEY'den okunur.

    `extra_params`, her isteğin gövdesine eklenir (örn. düşünmeyi kapatmak için modele özgü
    parametreler); çağrı başına `extra=` ile ezilebilir. `messages` ve `model` ezilemez.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "auto",
        api_key: str | None = None,
        post: Callable[[dict], dict] | None = None,
        *,
        extra_params: dict | None = None,
        timeout: float = 180.0,
        max_retries: int = 5,
        backoff: float = 5.0,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key or os.environ.get("EVREN_API_KEY", "")
        self.extra_params = dict(extra_params or {})
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.backoff = backoff
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep or time.sleep
        self._post = post or self._http_post

    def with_model(self, model: str, extra_params: dict | None = None, **kwargs: Any) -> "EvrenLLM":
        """Aynı adres ve anahtarla başka model için yeni istemci (zaman aşımı vb. ezilebilir)."""
        options: dict[str, Any] = {
            "extra_params": extra_params,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "backoff": self.backoff,
            "opener": self._opener,
            "sleep": self._sleep,
        }
        options.update(kwargs)
        return EvrenLLM(self.url.removesuffix("/chat/completions"), model, self.api_key, **options)

    def _payload(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        extra: dict | None = None,
        stream: bool = False,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        for params in (self.extra_params, extra or {}):
            for key, value in params.items():
                if key not in ("messages", "model", "stream"):
                    payload[key] = value
        return payload

    def _request(self, payload: dict) -> urllib.request.Request:
        if not self.api_key:
            raise LLMError("EVREN_API_KEY tanımlı değil")
        return urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    def _http_post(self, payload: dict) -> dict:
        req = self._request(payload)
        reason = "ulaşılamaz"
        for attempt in range(self.max_retries):
            delay = self.backoff * 2**attempt
            try:
                with self._opener(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code != 429 and e.code < 500:
                    raise LLMError(f"LLM isteği başarısız: HTTP {e.code}") from e
                reason = f"HTTP {e.code}"
                delay = _retry_after(e) or delay
            except (OSError, ValueError) as e:  # ağ kopması, zaman aşımı, bozuk gövde
                reason = type(e).__name__
            if attempt < self.max_retries - 1:
                self._sleep(delay)
        raise LLMError(f"LLM isteği başarısız: {reason}")

    def complete_detailed(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        *,
        extra: dict | None = None,
        reasoning_fallback: Callable[[str], str | None] | None = None,
        attempts: int = 3,
    ) -> Completion:
        """Boş içerik gelirse birkaç kez dener; 'length' ile kesilmişse max_tokens'ı artırır.

        Düşünen modeller cevabı `reasoning` alanına yazıp `content`'i boş bırakabilir.
        `reasoning_fallback(reasoning)` yalnızca bu durumda çağrılır; nihai cevabı açıkça bulabilirse
        metni, bulamazsa None döner (böylece düşünme taslağı yanlışlıkla cevap sayılmaz).
        """
        last = ""
        for _ in range(attempts):
            data = self._post(self._payload(messages, temperature, max_tokens, extra))
            comp = parse_completion(data)
            if comp.content:
                return comp
            if comp.reasoning and reasoning_fallback is not None:
                recovered = reasoning_fallback(comp.reasoning)
                if recovered and recovered.strip():
                    comp.content = recovered.strip()
                    return comp
            last = comp.describe()
            if comp.finish_reason == "length":
                max_tokens = min(max_tokens * 2, max(max_tokens, MAX_TOKENS_CAP))
        raise LLMError(f"LLM boş cevap verdi ({last})")

    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        *,
        extra: dict | None = None,
        reasoning_fallback: Callable[[str], str | None] | None = None,
    ) -> str:
        return self.complete_detailed(
            messages, temperature, max_tokens, extra=extra, reasoning_fallback=reasoning_fallback
        ).content

    def raw(self, messages: list[dict], max_tokens: int, extra: dict | None = None) -> dict:
        """Teşhis için ham cevabı döner."""
        return self._post(self._payload(messages, 0.3, max_tokens, extra))

    def stream_parts(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        *,
        extra: dict | None = None,
    ) -> Iterator[tuple[str, str]]:
        """Cevabı ("content" | "reasoning", metin) çiftleri olarak parça parça verir."""
        payload = self._payload(messages, temperature, max_tokens, extra, stream=True)
        try:
            with self._opener(self._request(payload), timeout=self.timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    content, reasoning = sse_parts(line)
                    if reasoning:
                        yield "reasoning", reasoning
                    if content:
                        yield "content", content
        except urllib.error.HTTPError as e:
            raise LLMError(f"LLM isteği başarısız: HTTP {e.code}") from e
        except (OSError, ValueError) as e:
            raise LLMError(f"LLM akışı kesildi: {type(e).__name__}") from e

    def stream(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        *,
        extra: dict | None = None,
    ) -> Iterator[str]:
        """Cevabı parça parça (SSE) verir; akıl yürütme ve <think> blokları atılır."""
        stripper = ThinkStripper()
        for kind, text in self.stream_parts(messages, temperature, max_tokens, extra=extra):
            if kind != "content":
                continue
            clean = stripper.feed(text)
            if clean:
                yield clean
        tail = stripper.flush()
        if tail:
            yield tail
