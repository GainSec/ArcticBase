from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCTIC_BASE_", env_file=".env", extra="ignore")

    data: Path = Field(default=Path("./data"))
    port: int = 2929
    host: str = "0.0.0.0"
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB
    frontend_dist: Path = Field(default=Path("../frontend/dist"))
    seed_data: Path = Field(default=Path("./seed"))


def get_settings() -> Settings:
    return Settings()
