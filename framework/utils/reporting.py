"""Reporting helpers that degrade gracefully.

Allure is optional. Everything here is a no-op when allure isn't installed or no
`--alluredir` was passed, so the framework never hard-depends on the reporter.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

try:  # pragma: no cover - import guard
    import allure
    from allure_commons.types import AttachmentType

    _ALLURE = True
except ImportError:  # pragma: no cover
    _ALLURE = False


def attach_text(name: str, content: str) -> None:
    if _ALLURE:
        allure.attach(content, name=name, attachment_type=AttachmentType.TEXT)


def attach_png(name: str, data: bytes) -> None:
    if _ALLURE:
        allure.attach(data, name=name, attachment_type=AttachmentType.PNG)


def attach_html(name: str, content: str) -> None:
    if _ALLURE:
        allure.attach(content, name=name, attachment_type=AttachmentType.HTML)


@contextlib.contextmanager
def step(title: str) -> Iterator[None]:
    """`with step("Log in as alice"):` — a report section, and a no-op without Allure.

    Steps are the difference between a report that says "test_checkout failed"
    and one that says "test_checkout failed at 'Place order'".
    """
    if _ALLURE:
        with allure.step(title):
            yield
    else:
        yield


def label(**kwargs: Any) -> None:
    """Attach Allure metadata (feature, story, severity, owner) without importing allure in tests."""
    if not _ALLURE:
        return
    for key, value in kwargs.items():
        allure.dynamic.label(key, str(value))
