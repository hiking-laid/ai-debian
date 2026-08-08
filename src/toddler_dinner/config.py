"""Application configuration.

Human-edited profile lives in a YAML config file; secrets (DSN, LLM key) come from env.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Exclusions(BaseModel):
    """Three-tier exclusions. allergies + dietary are HARD; dislikes are SOFT."""

    allergies: list[str] = Field(default_factory=list)
    dietary: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)


class Sex(str, Enum):
    FEMALE = "female"
    MALE = "male"


class ChildProfile(BaseModel):
    name: str = "child"
    birthdate: date
    sex: Sex = Sex.FEMALE  # used for WHO weight-for-age median lookup
    weight_kg: float
    activity_level: str = "moderate"  # low | moderate | high


class HouseholdProfile(BaseModel):
    location: str = "New Zealand"
    timezone: str = "Pacific/Auckland"  # IANA name; drives "today"/"tonight" and date windows
    # `budget` and `stores` belong with the future supermarket integration; omitted in v1.


class Profile(BaseModel):
    """The full human-edited profile loaded from the YAML config file."""

    child: ChildProfile
    household: HouseholdProfile
    exclusions: Exclusions = Field(default_factory=Exclusions)
    dinner_daily_fraction: float = 0.33
    variety_days: int = 5  # avoid repeating a dinner served within this many days
    history_days: int = 5  # how many days of cooked dinners to show in the history view
    # (snapshot_freshness_days omitted in v1 — returns with the future supermarket integration.)


class Secrets(BaseSettings):
    """Secrets/ops from environment (never in the profile file)."""

    model_config = SettingsConfigDict(env_prefix="TDP_", env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql+psycopg://localhost/toddler_dinner"
    # LLM provider selection + credentials.
    llm_provider: str = "copilot"  # copilot | openai | anthropic
    llm_model: str = "gpt-4o"
    llm_api_key: str | None = None       # OpenAI / Anthropic API key
    # Advanced/optional:
    llm_endpoint: str | None = None      # endpoint override (rarely needed)
    copilot_token: str | None = None     # pre-obtained Copilot token (else device-flow cache)
    web_port: int = 8080


def load_profile(path: str | Path) -> Profile:
    data = yaml.safe_load(Path(path).read_text())
    return Profile.model_validate(data)
