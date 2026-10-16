import json

import pytest
from fastapi.testclient import TestClient

from medrag import deps
from medrag.api.main import create_app
from medrag.api.routes import meta
from medrag.api.routes import speech as speech_route
from medrag.speech import SpeechClient, SpeechError, parse_transcript, sniff_audio

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 40
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 40


class FakeService:
    def stream(self, question, history):
        yield {"type": "done"}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDRAG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MEDRAG_EVAL_DIR", str(tmp_path / "eval"))
    monkeypatch.setenv("MEDRAG_ACCESS_LOG", "0")
    monkeypatch.setenv("MEDRAG_RATE_LIMIT_ENABLED", "0")
    deps.reset()
    meta._cache.clear()
    yield tmp_path
    deps.reset()


def client():
    return TestClient(create_app(FakeService()))


# --- geri bildirim ---
def test_feedback_persists_without_ip(env):
    c = client()
    r = c.post(
        "/api/feedback",
        json={"rating": 1, "page": "Chat", "question": "q", "answer": "a", "comment": " iyi "},
    )
    assert r.json() == {"ok": True}
    c.post("/api/feedback", json={"rating": -1, "page": "assess"})
    lines = (env / "feedback" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[0])
    assert rec["rating"] == 1 and rec["page"] == "chat" and rec["comment"] == "iyi" and rec["ts"]
    assert "ip" not in rec and "client" not in rec and len(lines) == 2
    s = c.get("/api/feedback/summary").json()
    assert s["total"] == 2 and s["ratings"] == {"up": 1, "down": 1}
    assert s["pages"]["assess"] == {"down": 1}


def test_feedback_validation(env):
    c = client()
    assert c.post("/api/feedback", json={"rating": 5, "page": "x"}).status_code == 422
    assert c.post("/api/feedback", json={"rating": 1, "comment": "x" * 1001}).status_code == 422
    assert c.post("/api/feedback", json={"rating": 1, "answer": "x" * 6001}).status_code == 422


def test_feedback_rotation(env, monkeypatch):
    monkeypatch.setenv("MEDRAG_FEEDBACK_MAX_BYTES", "300")
    monkeypatch.setenv("MEDRAG_FEEDBACK_KEEP", "2")
    deps.reset()
    c = client()
    for i in range(30):
        c.post("/api/feedback", json={"rating": 1, "page": "chat", "comment": f"yorum {i}"})
    d = env / "feedback"
    names = sorted(p.name for p in d.iterdir())
    assert names == ["feedback.jsonl", "feedback.jsonl.1", "feedback.jsonl.2"]
    assert (d / "feedback.jsonl").stat().st_size <= 300


def test_feedback_summary_protected_with_access_code(env, monkeypatch):
    monkeypatch.setenv("MEDRAG_ACCESS_CODE", "kod")
    c = client()
    assert c.get("/api/feedback/summary").status_code == 401
    assert c.get("/api/feedback/summary", headers={"X-Access-Code": "kod"}).status_code == 200


# --- meta ---
def test_meta_info_with_fixture_chunks(env):
    rows = [
        {"id": "1", "doc_id": "d1", "source": "medlineplus", "license": "PD"},
        {"id": "2", "doc_id": "d1", "source": "medlineplus", "license": "PD"},
        {"id": "3", "doc_id": "d2", "source": "wikipedia", "license": "CC-BY-SA"},
    ]
    (env / "chunks.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (env / "eval").mkdir()
    (env / "eval" / "results.md").write_text(
        "150 soru\n\n| yöntem | recall@1 | recall@3 | recall@5 | recall@10 | mrr@10 |\n|---|---|---|---|---|---|\n"
        "| vector | 0.647 | 0.760 | 0.847 | 0.940 | 0.730 |\n",
        encoding="utf-8",
    )
    (env / "eval" / "safety_results.md").write_text("**13/13 senaryo geçti**\n", encoding="utf-8")
    info = client().get("/api/meta/info").json()
    assert info["version"]
    assert info["sources"] == [
        {"source": "medlineplus", "license": "PD", "documents": 1, "chunks": 2},
        {"source": "wikipedia", "license": "CC-BY-SA", "documents": 1, "chunks": 1},
    ]
    assert info["models"]["embedding"] and info["models"]["chat"]
    assert info["eval"]["retrieval"]["questions"] == 150
    assert info["eval"]["retrieval"]["vector"]["recall@5"] == 0.847
    assert info["eval"]["safety"] == {"passed": 13, "total": 13}


def test_meta_info_missing_files_and_public_with_code(env, monkeypatch):
    monkeypatch.setenv("MEDRAG_ACCESS_CODE", "kod")
    info = client().get("/api/meta/info")
    assert info.status_code == 200
    assert info.json()["sources"] == [] and info.json()["eval"] == {}


# --- ses ---
class FakeSpeech(SpeechClient):
    def __init__(self, text="merhaba dünya", error=None):
        self.text, self.error, self.calls = text, error, []

    def transcribe(self, data, content_type):
        self.calls.append((len(data), content_type))
        if self.error:
            raise self.error
        return self.text


def speech_client(fake):
    app = create_app(FakeService())
    app.dependency_overrides[speech_route.get_speech_client] = lambda: fake
    return TestClient(app)


def test_speech_transcribe_ok(env):
    fake = FakeSpeech()
    r = speech_client(fake).post(
        "/api/speech/transcribe", files={"file": ("a.webm", WEBM, "audio/webm;codecs=opus")}
    )
    assert r.status_code == 200 and r.json() == {"text": "merhaba dünya"}
    assert fake.calls == [(len(WEBM), "audio/webm")]


def test_speech_rejects_bad_type_magic_empty_and_large(env, monkeypatch):
    monkeypatch.setenv("MEDRAG_SPEECH_MAX_BYTES", "100")
    deps.reset()
    c = speech_client(FakeSpeech())
    post = lambda name, data, ctype: c.post(
        "/api/speech/transcribe", files={"file": (name, data, ctype)}
    )
    assert post("a.txt", b"hi", "text/plain").status_code == 415
    assert post("a.wav", b"not audio at all, just text", "audio/wav").status_code == 415
    assert post("a.wav", b"", "audio/wav").status_code == 400
    r = post("a.wav", WAV + b"\x00" * 200, "audio/wav")
    assert r.status_code == 413 and "büyük" in r.json()["message"]
    assert c.post("/api/speech/transcribe").status_code == 422


def test_speech_errors_are_json_turkish(env):
    r = speech_client(FakeSpeech(error=SpeechError("Ses tanıma servisine ulaşılamadı"))).post(
        "/api/speech/transcribe", files={"file": ("a.wav", WAV, "audio/wav")}
    )
    assert r.status_code == 502 and r.json()["error"] == "speech_failed"
    r = speech_client(FakeSpeech(text="")).post(
        "/api/speech/transcribe", files={"file": ("a.wav", WAV, "audio/wav")}
    )
    assert r.status_code == 422 and r.json()["error"] == "no_speech"


def test_speech_upload_hits_upload_budget(env, monkeypatch):
    monkeypatch.setenv("MEDRAG_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("MEDRAG_RATE_UPLOAD_BURST", "1")
    monkeypatch.setenv("MEDRAG_RATE_UPLOAD_PER_MIN", "1")
    c = speech_client(FakeSpeech())
    f = {"file": ("a.wav", WAV, "audio/wav")}
    assert c.post("/api/speech/transcribe", files=f).status_code == 200
    assert c.post("/api/speech/transcribe", files=f).status_code == 429


# --- ses istemcisi ---
def test_sniff_audio():
    assert sniff_audio(WAV) == "audio/wav" and sniff_audio(WEBM) == "audio/webm"
    assert sniff_audio(b"OggS" + b"\x00" * 20) == "audio/ogg"
    assert sniff_audio(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8) == "audio/mp4"
    assert sniff_audio(b"ID3\x04" + b"\x00" * 20) == "audio/mpeg"
    assert sniff_audio(b"hello world, text") is None


def test_parse_transcript_variants():
    assert parse_transcript(b'{"text": " selam "}') == "selam"
    assert parse_transcript({"choices": [{"message": {"content": "language Turkish<asr_text>Merhaba"}}]}) == "Merhaba"
    assert parse_transcript("düz metin") == "düz metin"
    assert parse_transcript({"choices": [{"message": {"content": [{"type": "text", "text": "x"}]}}]}) == "x"
    with pytest.raises(SpeechError):
        parse_transcript({"foo": 1})


def test_speech_client_multipart_and_fallback():
    from medrag.speech import HttpError

    seen = []

    def post(url, body, headers, timeout):
        seen.append((url, headers["Content-Type"], body))
        if url.endswith("/audio/transcriptions"):
            raise HttpError(404)
        return b'{"choices":[{"message":{"content":"tamam"}}]}'

    c = SpeechClient("http://x/v1/", api_key="k", post=post)
    assert c.transcribe(WAV, "audio/wav") == "tamam"
    assert seen[0][1].startswith("multipart/form-data; boundary=")
    assert b'name="model"' in seen[0][2] and b"qwen3-asr-1.7b" in seen[0][2] and WAV in seen[0][2]
    assert seen[1][0] == "http://x/v1/chat/completions"
    with pytest.raises(SpeechError):
        SpeechClient("http://x", api_key="", post=post).transcribe(WAV, "audio/wav")

    def denied(url, body, headers, timeout):
        raise HttpError(401)

    with pytest.raises(SpeechError, match="reddetti"):
        SpeechClient("http://x", api_key="k", post=denied).transcribe(WAV, "audio/wav")
