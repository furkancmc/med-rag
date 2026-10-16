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
    embed_batch_size: int = 64  # istek başına metin
    embed_workers: int = 16  # paralel embedding isteği
    index_max_float16_mb: int = 40  # float16 bunu aşacaksa int8 sakla
    europepmc_per_topic: int = 3  # Europe PMC: konu başına makale

    # --- Sohbet ve güvenlik (iş akışı C) ---
    llm_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    llm_model: str = "auto"

    # --- Belirti değerlendirme (iş akışı D) ---

    # --- Tahlil ve görsel okuma (iş akışı E) ---

    # --- Sunucu (iş akışı F) ---


def get_settings() -> Settings:
    return Settings()
