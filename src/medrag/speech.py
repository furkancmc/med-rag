"""Ses tanıma istemcisi (Evren API, qwen3-asr). Ses asla diske yazılmaz ve loglanmaz.

API biçimi doğrulanmadığı için iki yol desteklenir: OpenAI uyumlu `/audio/transcriptions`
(multipart) ve yedek olarak `/chat/completions` (input_audio). Cevap ayrıştırma toleranslıdır.
"""

import base64
import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable

AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"}
# "audio/x-wav", "audio/mp3" gibi yaygın takma adlar
ALIASES = {
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/mp3": "audio/mpeg",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
}
EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
}
CHAT_FORMATS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4",
                "audio/mpeg": "mp3", "audio/wav": "wav"}


class SpeechError(RuntimeError):
    pass


def normalize_type(content_type: str | None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    return ALIASES.get(base, base)


def sniff_audio(data: bytes) -> str | None:
    """Sihirli baytlardan ses türünü bulur; tanınmazsa None."""
    head = data[:16]
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    if head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    return None


def build_multipart(fields: dict[str, str], filename: str, content_type: str, data: bytes):
    """(gövde, content-type başlığı) döner."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
        ).encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def parse_transcript(raw: bytes | str | dict) -> str:
    """Çeşitli cevap biçimlerinden metni çıkarır: {"text"}, chat cevabı ya da düz metin."""
    data = raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError:
            return clean_text(raw)
    if isinstance(data, dict):
        if isinstance(data.get("text"), str):
            return clean_text(data["text"])
        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return clean_text(str(content or ""))
        except (KeyError, IndexError, TypeError):
            pass
    if isinstance(data, str):
        return clean_text(data)
    raise SpeechError("Ses tanıma cevabı anlaşılamadı")


def clean_text(text: str) -> str:
    """qwen-asr çıktısındaki 'language Turkish<asr_text>...' önekini atar."""
    if "<asr_text>" in text:
        text = text.split("<asr_text>", 1)[1]
    return text.strip()


class HttpError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code


def _urlopen_post(url: str, body: bytes, headers: dict, timeout: float) -> bytes:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SpeechError("Ses tanıma servisine ulaşılamadı") from e


class SpeechClient:
    """`post(url, body, headers, timeout) -> bytes` enjekte edilebilir (testlerde sahte)."""

    def __init__(
        self,
        base_url: str,
        model: str = "qwen3-asr-1.7b",
        language: str = "tr",
        mode: str = "auto",
        timeout: float = 60.0,
        api_key: str | None = None,
        post: Callable[[str, bytes, dict, float], bytes] | None = None,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.model = model
        self.language = language
        self.mode = mode
        self.timeout = timeout
        self.api_key = api_key if api_key is not None else os.environ.get("EVREN_API_KEY", "")
        self._post = post or _urlopen_post

    def _auth(self) -> dict:
        if not self.api_key:
            raise SpeechError("EVREN_API_KEY tanımlı değil")
        return {"Authorization": f"Bearer {self.api_key}"}

    def _transcriptions(self, data: bytes, content_type: str) -> bytes:
        fields = {"model": self.model, "response_format": "json"}
        if self.language:
            fields["language"] = self.language
        body, ctype = build_multipart(
            fields, f"ses.{EXTENSIONS.get(content_type, 'bin')}", content_type, data
        )
        headers = {**self._auth(), "Content-Type": ctype}
        return self._post(self.base + "/audio/transcriptions", body, headers, self.timeout)

    def _chat(self, data: bytes, content_type: str) -> bytes:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64.b64encode(data).decode("ascii"),
                                "format": CHAT_FORMATS.get(content_type, "wav"),
                            },
                        }
                    ],
                }
            ],
            "temperature": 0.0,
        }
        headers = {**self._auth(), "Content-Type": "application/json"}
        return self._post(
            self.base + "/chat/completions", json.dumps(payload).encode(), headers, self.timeout
        )

    def transcribe(self, data: bytes, content_type: str) -> str:
        """Sesi metne çevirir; hata olursa SpeechError (Türkçe mesajlı) fırlatır."""
        modes = {"transcriptions": ["t"], "chat": ["c"], "auto": ["t", "c"]}.get(self.mode, ["t", "c"])
        last: Exception | None = None
        for m in modes:
            try:
                raw = self._transcriptions(data, content_type) if m == "t" else self._chat(
                    data, content_type
                )
                return parse_transcript(raw)
            except HttpError as e:
                last = e
                if e.code in (401, 403):
                    raise SpeechError("Ses tanıma servisi erişimi reddetti") from e
                continue  # 404/400/422...: diğer yolu dene
            except SpeechError as e:
                last = e
                if "ulaşılamadı" in str(e) or "EVREN_API_KEY" in str(e):
                    raise
                continue
        raise SpeechError("Ses tanıma şu an başarısız oldu") from last
