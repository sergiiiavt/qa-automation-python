"""Unit tests for framework/config.py's source precedence and strictness.

No SUT, browser, or Appium session needed — these exercise Settings directly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framework.config import ApiSettings, Settings


def test_real_env_var_beats_yaml_init_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: Settings.load() passes YAML as init kwargs, and Pydantic
    Settings' default source order ranks init kwargs above env vars. Without the
    explicit `settings_customise_sources` override, this would silently reverse
    the documented `env > .env > YAML > defaults` precedence."""
    monkeypatch.setenv("QA_API__TIMEOUT", "99")

    settings = Settings(api=ApiSettings(timeout=5.0))

    assert settings.api.timeout == 99.0


def test_yaml_init_kwargs_apply_when_no_env_var_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QA_API__TIMEOUT", raising=False)

    settings = Settings(api=ApiSettings(timeout=5.0))

    assert settings.api.timeout == 5.0


def test_field_default_applies_when_no_source_sets_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QA_API__TIMEOUT", raising=False)

    settings = Settings()

    assert settings.api.timeout == 10.0


def test_unknown_top_level_key_is_a_startup_error() -> None:
    with pytest.raises(ValidationError):
        Settings(**{"not_a_real_field": 1})


def test_unknown_nested_yaml_key_is_a_startup_error() -> None:
    with pytest.raises(ValidationError):
        Settings(**{"api": {"timeuot": 5}})  # realistic typo, not just a random key


def test_misspelled_nested_env_var_is_a_startup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo inside a nested group (api__, web__, mobile__, user__) IS caught:
    the nested-delimiter env source explodes everything under `QA_API__` into
    a dict — typo included — and hands it to ApiSettings, which now rejects
    unknown keys. This mirrors the YAML-typo case, not the top-level case
    below."""
    monkeypatch.setenv("QA_API__TIMOUT", "99")  # missing the "E" in TIMEOUT

    with pytest.raises(ValidationError):
        Settings()


def test_misspelled_top_level_env_var_is_silently_unused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike the nested case above, a typo in a *top-level* field's env var
    name is not caught. Top-level env lookup matches known field names
    exactly (there's no delimiter to explode), so an unrecognized name like
    QA_ENVX is simply never read — `env` silently keeps its next-lower-
    priority value instead of raising."""
    monkeypatch.setenv("QA_ENVX", "dev")  # missing the "V", meant QA_ENV

    settings = Settings()

    assert settings.env.value == "local"
