"""Typed, layered configuration.

Rule of the course: **no test ever reads os.environ directly.** Every knob is a
field on `Settings`, so:
  * a typo becomes a startup error, not a mysterious `None` at 3 a.m.;
  * `settings.api.base_url` autocompletes and type-checks;
  * switching environments is one variable (`QA_ENV`), not a sed across the repo.

Precedence (highest first): real env vars -> .env file -> per-env YAML -> defaults.
"""

from __future__ import annotations

import functools
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


class Env(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"


class ApiSettings(BaseModel):
    base_url: str = "http://127.0.0.1:8000"
    timeout: float = 10.0
    retries: int = Field(default=2, ge=0, le=5)
    verify_ssl: bool = True


class WebSettings(BaseModel):
    base_url: str = "http://127.0.0.1:8000"
    browser: str = "chromium"
    headless: bool = True
    slow_mo: int = 0
    viewport_width: int = 1280
    viewport_height: int = 800
    # Default per-action timeout. Playwright's own default is 30s; 10s surfaces
    # slowness as a failure instead of hiding it behind a long wait.
    action_timeout_ms: int = 10_000
    navigation_timeout_ms: int = 20_000


class MobileSettings(BaseModel):
    appium_url: str = "http://127.0.0.1:4723"
    platform: Platform = Platform.ANDROID
    device_name: str = "Pixel_7_API_34"
    platform_version: str = "14"
    app_path: str | None = None
    mobile_browser: str | None = None       # set -> drive the browser, not an app
    new_command_timeout: int = 120
    # Real-device cloud (BrowserStack / Sauce / LambdaTest). Empty -> local Appium.
    cloud_user: str | None = None
    cloud_key: str | None = None

    @field_validator("app_path")
    @classmethod
    def _absolutize(cls, v: str | None) -> str | None:
        if v is None:
            return None
        p = Path(v)
        return str(p if p.is_absolute() else (ROOT / p).resolve())


class UserSettings(BaseModel):
    name: str = "alice"
    password: str = "wonderland"


class Settings(BaseSettings):
    """Root settings object. Import `settings` (the cached singleton) in tests."""

    model_config = SettingsConfigDict(
        env_prefix="QA_",
        env_nested_delimiter="__",   # QA_API__TIMEOUT=5 also works
        env_file=(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Env = Env.LOCAL
    api: ApiSettings = ApiSettings()
    web: WebSettings = WebSettings()
    mobile: MobileSettings = MobileSettings()
    user: UserSettings = UserSettings()

    artifacts_dir: Path = ROOT / "artifacts"

    @property
    def is_local(self) -> bool:
        return self.env is Env.LOCAL

    @classmethod
    def load(cls) -> Settings:
        """Merge config/<env>.yaml under the env vars, then validate."""
        env_name = _raw_env_value()
        overrides: dict = {}
        yaml_path = CONFIG_DIR / f"{env_name}.yaml"
        if yaml_path.exists():
            overrides = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        # BaseSettings applies env vars *on top* of the kwargs we pass, so YAML
        # acts as the lower-priority layer exactly as advertised.
        return cls(**overrides)


def _raw_env_value() -> str:
    import os

    return os.getenv("QA_ENV", Env.LOCAL.value).lower()


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


settings = get_settings()
