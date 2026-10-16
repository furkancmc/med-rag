from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MEDRAG_", extra="ignore")

    model: str = "claude-sonnet-5-5"
    data_dir: Path = Path("data")
    embedding_model: str = "intfloat/multilingual-e5-small"
    top_k: int = 5
    embed_provider: str = "api"  # api | local
    embed_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    embed_api_model: str = "qwen3-embedding-8b"
    embed_dimensions: int = 1024


def get_settings() -> Settings:
    return Settings()
