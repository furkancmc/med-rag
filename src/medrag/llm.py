import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator


class LLMError(RuntimeError):
    pass


class EvrenLLM:
    """OpenAI uyumlu /chat/completions istemcisi (Evren API). Anahtar EVREN_API_KEY'den okunur."""

    def __init__(
        self,
        base_url: str,
        model: str = "auto",
        api_key: str | None = None,
        post: Callable[[dict], dict] | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key or os.environ.get("EVREN_API_KEY", "")
        self._post = post or self._http_post

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
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if (e.code != 429 and e.code < 500) or attempt == 4:
                    raise LLMError(f"LLM isteği başarısız: HTTP {e.code}") from e
                time.sleep(5 * 2**attempt)
        raise LLMError("ulaşılamaz")

    def complete(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._post(payload)
        try:
            choice = data["choices"][0]
            content = choice["message"].get("content")
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise LLMError(f"Beklenmeyen LLM cevabı: {str(data)[:200]}") from e
        if not content or not content.strip():
            # Düşünen modellerde token sınırı iç düşünmeye harcanırsa içerik boş gelebilir.
            raise LLMError(f"LLM boş cevap verdi (finish_reason={choice.get('finish_reason')})")
        return content.strip()

    def raw(self, messages: list[dict], max_tokens: int) -> dict:
        """Teşhis için ham cevabı döner."""
        return self._post(
            {"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens}
        )

    def stream(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> Iterator[str]:
        """Cevabı parça parça (SSE) verir."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            with urllib.request.urlopen(self._request(payload), timeout=180) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        return
                    delta = json.loads(body)["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
        except urllib.error.HTTPError as e:
            raise LLMError(f"LLM isteği başarısız: HTTP {e.code}") from e
