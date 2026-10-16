from medrag.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_model == "auto"
    assert s.embed_dimensions == 1024
    assert s.top_k == 5


def test_env_override(monkeypatch):
    monkeypatch.setenv("MEDRAG_TOP_K", "8")
    assert Settings(_env_file=None).top_k == 8
