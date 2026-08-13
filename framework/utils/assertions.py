"""Assertion helpers.

Plain `assert` is the default in pytest and it is good — the rewritten
introspection output is excellent. These helpers exist for the two cases plain
assert handles badly.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

import jsonschema
import pytest_check as check

T = TypeVar("T")


def soft(condition: bool, message: str) -> None:
    """Record a failure but keep going.

    Use for *independent* observations in one scenario — "the price is wrong AND
    the badge is wrong AND the total is wrong" is three findings from one run.
    Do NOT use it for preconditions: if login failed, everything after it is
    noise, and a hard assert gives a shorter path to the cause.
    """
    check.is_true(condition, message)


def assert_matches_schema(payload: Any, schema: dict) -> None:
    """Validate against a JSON Schema with a readable failure.

    pydantic covers the models you own. Raw JSON Schema is for the contracts you
    *don't* own — a partner API, or a schema file the backend team publishes.
    """
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise AssertionError(
            f"Schema violation at '{location}': {exc.message}\n"
            f"Payload: {json.dumps(payload, indent=2)[:1500]}"
        ) from None


def assert_status(response: Any, expected: int) -> None:
    assert response.status_code == expected, (
        f"{response.request.method} {response.request.url}\n"
        f"expected {expected}, got {response.status_code}\nbody: {response.text[:1000]}"
    )


def eventually(
    predicate: Callable[[], T],
    *,
    timeout: float = 10.0,
    interval: float = 0.25,
    message: str = "Condition not met",
) -> T:
    """Poll until truthy. The *only* sanctioned wait outside the UI layers.

    For asynchronous backends (a message lands on a queue, a projection catches
    up), there is no locator to auto-wait on. Everywhere else, prefer the
    framework's built-in waiting.
    """
    import time

    deadline = time.monotonic() + timeout
    last: T | None = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"{message} (waited {timeout}s, last value: {last!r})")


def approx_money(value: float, expected: float, tolerance: float = 0.01) -> None:
    """Currency comparison. Never `==` on floats that came from money maths."""
    assert abs(value - expected) <= tolerance, (
        f"Expected {expected:.2f} +/- {tolerance}, got {value:.2f}"
    )
