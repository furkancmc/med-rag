from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MEDRAG_", extra="ignore")

    model: str = "claude-sonnet-5-5"
    data_dir: Path = Path("data")
    embedding_model: str = "intfloat/multilingual-e5-small"
    top_k: int = 5


def get_settings() -> Settings:
    return Settings()
