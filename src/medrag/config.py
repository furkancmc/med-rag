from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MEDRAG_", extra="ignore")

    data_dir: Path = Path("data")
    top_k: int = 5
    embed_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    embed_api_model: str = "qwen3-embedding-8b"
    embed_dimensions: int = 1024
    index_dir: Path = Path("data/index_qwen3")
    llm_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    llm_model: str = "auto"


def get_settings() -> Settings:
    return Settings()
