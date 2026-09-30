from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIOT_", extra="ignore")

    api_key: SecretStr = SecretStr("")
    region: Literal["americas", "europe", "asia", "sea"] = "americas"
    timeout_seconds: float = Field(default=5, gt=0, le=30)
    max_attempts: int = Field(default=3, ge=1, le=3)
