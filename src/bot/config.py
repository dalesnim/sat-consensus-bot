from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    id: str
    lab: str
    reasoning: Literal["none", "minimal", "low", "omit"]
    est_cost_usd: float = Field(default=0.0, ge=0)
    in_reduced_set: bool = False


class RosterConfig(BaseModel):
    models: list[ModelConfig] = Field(min_length=1)
    min_distinct_labs: int = Field(ge=1)
    max_tokens: int = Field(gt=0)
    tiebreakers: list[list[str]] = Field(default_factory=list)
    tiebreak_model: ModelConfig | None = None

    @property
    def reduced_models(self) -> list[ModelConfig]:
        return [m for m in self.models if m.in_reduced_set]

    def estimate_usd(self, models: Sequence[ModelConfig], *, multiplier: float) -> float:
        return sum(m.est_cost_usd for m in models) * multiplier


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: SecretStr
    openrouter_api_key: SecretStr
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    models_config_path: Path = Path("models.yaml")
    db_path: Path = Path("data/bot.db")
    per_model_timeout_seconds: int = 47
    round_timeout_seconds: int = 50
    min_valid_responses: int = 3
    max_image_bytes: int = 10485760
    min_image_dimension: int = 600
    blur_variance_warn: float = 120.0
    blur_variance_reject: float = 40.0
    log_level: str = "INFO"
    debug_log_raw_bodies: bool = False
    owner_id: int | None = None
    allowed_user_ids: str = ""
    per_user_daily_cap: int = 40
    daily_spend_cap_usd: float = 1000.0
    round_cost_safety_multiplier: float = 1.25

    @property
    def allowlist_ids(self) -> frozenset[int]:
        return frozenset(
            int(part.strip()) for part in self.allowed_user_ids.split(",") if part.strip()
        )


def load_roster(path: Path) -> RosterConfig:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RosterConfig.model_validate(data)


def load_settings() -> Settings:
    return Settings()
