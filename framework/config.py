"""Typed, layered configuration.

Rule of the course: **no test ever reads os.environ directly.** Every knob is a
field on `Settings`, so:
  * an unknown key in per-env YAML becomes a startup error naming the field,
    not a mysterious `None` at 3 a.m. (a misspelled *env var name* is a
    different failure mode — see the precedence note below);
  * `settings.api.base_url` autocompletes and type-checks;
  * switching environments is one variable (`QA_ENV`), not a sed across the repo.

Precedence (highest first): real env vars -> .env file -> per-env YAML -> defaults.
This is enforced explicitly in `settings_customise_sources` below — Pydantic
Settings' own default order ranks constructor kwargs (which is how the YAML
layer is applied) *above* environment variables, so without that override the
precedence documented here would silently be wrong.

Caveat: `extra="forbid"` catches a typo inside a nested group (e.g. an env var
misspelled `QA_API__TIMOUT`, or a bad key under `api:` in YAML) because the
nested-delimiter env source explodes everything under that prefix into a
dict and hands the whole thing to `ApiSettings`, typo included. It does
*not* catch a typo in a **top-level** field name (e.g. `QA_ENVX` instead of
`QA_ENV`): top-level env lookup matches known field names exactly, so an
unrecognized top-level name is simply never read — the field just keeps its
next-lower-priority value, with no error. See tests/framework/test_config.py
for both cases made concrete.
"""

from __future__ import annotations

import functools
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

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


class _StrictModel(BaseModel):
    """Base for nested settings groups: an unknown YAML key under this group
    is a startup error, matching the top-level `Settings.model_config`."""

    model_config = ConfigDict(extra="forbid")


class ApiSettings(_StrictModel):
    base_url: str = "http://127.0.0.1:8000"
    timeout: float = 10.0
    retries: int = Field(default=2, ge=0, le=5)
    verify_ssl: bool = True


class WebSettings(_StrictModel):
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


class MobileSettings(_StrictModel):
    appium_url: str = "http://127.0.0.1:4723"
    platform: Platform = Platform.ANDROID
    device_name: str = "Pixel_7_API_34"
    platform_version: str = "14"
    # Sauce Labs' MIT-licensed "My Demo App" — see apps/README.md. Bundled so
    # tests/mobile runs offline, the same way sut/ keeps the web+API layers
    # offline. Point this elsewhere for your own app.
    app_path: str | None = "apps/mda-2.2.0-25.apk"
    mobile_browser: str | None = None  # set -> drive the browser, not an app
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


class UserSettings(_StrictModel):
    name: str = "alice"
    password: str = "wonderland"


class Settings(BaseSettings):
    """Root settings object. Import `settings` (the cached singleton) in tests."""

    model_config = SettingsConfigDict(
        env_prefix="QA_",
        env_nested_delimiter="__",  # QA_API__TIMEOUT=5 also works
        env_file=(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="forbid",  # unknown YAML keys fail startup instead of vanishing silently
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
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Pydantic Settings' default order is (init, env, dotenv, secrets) —
        # init kwargs win. We pass the YAML layer as init kwargs (see `load`
        # below), so without this override YAML would silently outrank real
        # env vars and the .env file, the opposite of the documented policy.
        # Rank explicitly: env vars > .env file > YAML (init) > secrets.
        return (env_settings, dotenv_settings, init_settings, file_secret_settings)

    @classmethod
    def load(cls) -> Settings:
        """Merge config/<env>.yaml under the env vars, then validate."""
        env_name = _raw_env_value()
        overrides: dict[str, Any] = {}
        yaml_path = CONFIG_DIR / f"{env_name}.yaml"
        if yaml_path.exists():
            overrides = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        # `overrides` is passed as init kwargs; settings_customise_sources
        # above is what actually keeps this layer below env vars and .env.
        return cls(**overrides)


def _raw_env_value() -> str:
    import os

    return os.getenv("QA_ENV", Env.LOCAL.value).lower()


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


settings = get_settings()
