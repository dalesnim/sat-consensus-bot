from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    id: str
    lab: str
    reasoning: Literal["none", "minimal", "low", "omit"]


class RosterConfig(BaseModel):
    models: list[ModelConfig] = Field(min_length=1)
    min_distinct_labs: int = Field(ge=1)
    max_tokens: int = Field(gt=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: SecretStr
    openrouter_api_key: SecretStr
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    models_config_path: Path = Path("models.yaml")
    per_model_timeout_seconds: int = 42
    round_timeout_seconds: int = 45
    min_valid_responses: int = 3
    max_image_bytes: int = 10485760
    min_image_dimension: int = 600
    blur_variance_warn: float = 120.0
    blur_variance_reject: float = 40.0
    log_level: str = "INFO"
    debug_log_raw_bodies: bool = False


def load_roster(path: Path) -> RosterConfig:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RosterConfig.model_validate(data)


def load_settings() -> Settings:
    return Settings()
