from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tüm ayarlar `MEDRAG_` önekli ortam değişkenleriyle değiştirilebilir.

    Her iş akışı kendi alanlarını kendi bloğunun altına ekler (paralel geliştirmede çakışmasın diye).
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MEDRAG_", extra="ignore")

    # --- Genel ---
    data_dir: Path = Path("data")
    top_k: int = 5

    # --- Arama ve embedding (iş akışı A) ---
    embed_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    embed_api_model: str = "qwen3-embedding-8b"
    embed_dimensions: int = 1024
    index_dir: Path = Path("data/index_qwen3")

    # --- Veri (iş akışı B) ---

    # --- Sohbet ve güvenlik (iş akışı C) ---
    llm_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    llm_model: str = "auto"
    llm_extra_params: str = ""  # JSON; cevap modeline her isteğe eklenir (örn. düşünmeyi kapatma)
    answer_max_tokens: int = 4096  # düşünen modeller token harcar; cömert tutulur
    # Çalışma anında cevap doğrulama
    verify_enabled: bool = True
    verify_model: str = "deepseek-v4.1-flash"
    verify_extra_params: str = '{"chat_template_kwargs": {"enable_thinking": false}}'
    verify_budget_seconds: float = 20.0
    verify_group_size: int = 3
    verify_concurrency: int = 8
    # İkinci katman acil durum / zararlı istek sınıflandırıcısı
    classifier_enabled: bool = True
    guard_model: str = ""  # örn. qwen3-guard-4b; boşsa koruma modeli kullanılmaz (maliyet için kapalı)
    classifier_model: str = "deepseek-v4.1-flash"  # boş bırakılırsa LLM sınıflandırıcı kullanılmaz
    classifier_extra_params: str = '{"chat_template_kwargs": {"enable_thinking": false}}'
    classifier_timeout_seconds: float = 8.0

    # --- Belirti değerlendirme (iş akışı D) ---

    # --- Tahlil ve görsel okuma (iş akışı E) ---

    # --- Sunucu (iş akışı F) ---


def get_settings() -> Settings:
    return Settings()
