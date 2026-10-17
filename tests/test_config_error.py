import pytest
from fastapi.testclient import TestClient

from medrag import deps
from medrag.api.main import create_app
from medrag.config import ConfigError, Settings
from medrag.llm import EvrenLLM, LLMError, MissingKeyError
from medrag.retrieve import load_retriever


def test_missing_key_is_config_error(monkeypatch, tmp_path):
    monkeypatch.delenv("EVREN_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        load_retriever(Settings(data_dir=tmp_path, embed_backend="api"))


def test_llm_missing_key_is_both_llm_and_config_error(monkeypatch):
    monkeypatch.delenv("EVREN_API_KEY", raising=False)
    with pytest.raises(MissingKeyError) as info:
        EvrenLLM("http://x", "m").complete([{"role": "user", "content": "a"}])
    assert isinstance(info.value, LLMError) and isinstance(info.value, ConfigError)


def test_api_returns_503_instead_of_crashing_without_key(monkeypatch):
    monkeypatch.setenv("MEDRAG_EMBED_BACKEND", "api")  # yerel arka uç anahtar istemez
    monkeypatch.delenv("EVREN_API_KEY", raising=False)
    deps.reset()
    client = TestClient(create_app(), raise_server_exceptions=True)
    resp = client.post("/api/assess/start", json={"complaint": "iki gündür başım ağrıyor"})
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "config_error" and "EVREN_API_KEY" in body["message"]
    deps.reset()
