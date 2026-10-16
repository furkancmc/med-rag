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

    # --- Belirti değerlendirme (iş akışı D) ---

    # --- Tahlil ve görsel okuma (iş akışı E) ---

    # --- Sunucu (iş akışı F) ---


def get_settings() -> Settings:
    return Settings()
