from medrag.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.model == "claude-sonnet-5-5"
    assert s.top_k == 5


def test_env_override(monkeypatch):
    monkeypatch.setenv("MEDRAG_TOP_K", "8")
    assert Settings(_env_file=None).top_k == 8
