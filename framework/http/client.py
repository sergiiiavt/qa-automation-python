"""HTTP transport layer.

Design intent: **one place** owns retries, timeouts, logging and Allure
attachments. Service objects (framework/api/*.py) know endpoints and models;
they must not know about transport concerns.

Why httpx over requests:
  * first-class HTTP/2 and async, same sync API surface;
  * `event_hooks` give clean request/response instrumentation;
  * `respx` mocks it, so the framework itself is unit-testable.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Self

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from framework.config import settings
from framework.utils.reporting import attach_text

log = logging.getLogger("framework.http")

# Only these are safe to retry blindly. Retrying a POST can double-charge a card;
# idempotency must be proven, never assumed.
IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}
RETRYABLE_STATUS = {429, 502, 503, 504}


class ApiError(AssertionError):
    """Raised when a response fails an expected-status check.

    Inherits AssertionError so pytest renders it as a failure, not an error —
    a wrong status code is a test failure, not an infrastructure crash.
    """

    def __init__(self, response: httpx.Response, expected: int | tuple[int, ...]):
        self.response = response
        body = response.text[:2000]
        super().__init__(
            f"{response.request.method} {response.request.url} -> {response.status_code} "
            f"(expected {expected})\n{body}"
        )


class RetryableStatus(Exception):
    """Internal signal used by tenacity; never leaks to tests."""


class ApiClient:
    """Thin, instrumented wrapper around httpx.Client."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = (base_url or settings.api.base_url).rstrip("/")
        self.retries = settings.api.retries if retries is None else retries
        self._token = token
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout or settings.api.timeout,
            verify=settings.api.verify_ssl,
            headers={"Accept": "application/json", **(headers or {})},
            follow_redirects=True,
            event_hooks={"response": [self._log_response]},
        )

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- auth --------------------------------------------------------------
    @property
    def token(self) -> str | None:
        return self._token

    def with_token(self, token: str) -> Self:
        """Return *this* client authenticated. Chainable: client.with_token(t).get(...)"""
        self._token = token
        self._client.headers["Authorization"] = f"Bearer {token}"
        return self

    def anonymous(self) -> Self:
        self._token = None
        self._client.headers.pop("Authorization", None)
        return self

    # -- core --------------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        expect: int | tuple[int, ...] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request; optionally assert the status code.

        `expect` turns the extremely common two-line pattern
            r = client.get(...); assert r.status_code == 200
        into one call that also produces a useful failure message.
        """
        response = self._send_with_retries(method, url, **kwargs)
        if expect is not None:
            allowed = (expect,) if isinstance(expect, int) else expect
            if response.status_code not in allowed:
                raise ApiError(response, expect)
        return response

    def _send_with_retries(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempts = self.retries + 1 if method.upper() in IDEMPOTENT_METHODS else 1

        @retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential_jitter(initial=0.2, max=3),
            retry=retry_if_exception_type((RetryableStatus, httpx.TransportError)),
            reraise=True,
        )
        def _do() -> httpx.Response:
            response = self._client.request(method, url, **kwargs)
            if response.status_code in RETRYABLE_STATUS and attempts > 1:
                raise RetryableStatus(f"{response.status_code} from {url}")
            return response

        try:
            return _do()
        except RetryableStatus:
            # Exhausted retries on a retryable status: return the last response so
            # the assertion (and the report) shows the real server answer.
            return self._client.request(method, url, **kwargs)

    # Convenience verbs -----------------------------------------------------
    def get(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("POST", url, **kw)

    def put(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("PUT", url, **kw)

    def patch(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("PATCH", url, **kw)

    def delete(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("DELETE", url, **kw)

    # -- instrumentation ---------------------------------------------------
    @staticmethod
    def _log_response(response: httpx.Response) -> None:
        response.read()  # event hooks run before the body is consumed
        request = response.request
        elapsed_ms = response.elapsed.total_seconds() * 1000
        log.info(
            "%s %s -> %s (%.0f ms)", request.method, request.url, response.status_code, elapsed_ms
        )

        body = _pretty(request.content)
        attach_text(
            name=f"{request.method} {request.url.path} [{response.status_code}]",
            content=(
                f"--- REQUEST ---\n{request.method} {request.url}\n"
                f"{_headers(dict(request.headers))}\n\n{body}\n\n"
                f"--- RESPONSE ({elapsed_ms:.0f} ms) ---\n{response.status_code}\n"
                f"{_headers(dict(response.headers))}\n\n{_pretty(response.content)}"
            ),
        )


SENSITIVE = {"authorization", "cookie", "set-cookie", "x-api-key"}


def _headers(headers: dict[str, str]) -> str:
    """Never let a bearer token reach a report artifact."""
    return "\n".join(
        f"{k}: {'***REDACTED***' if k.lower() in SENSITIVE else v}" for k, v in headers.items()
    )


def _pretty(raw: bytes) -> str:
    if not raw:
        return "<empty body>"
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)[:8000]
    except (ValueError, UnicodeDecodeError):
        return raw[:2000].decode("utf-8", errors="replace")


def wait_for_service(url: str, timeout: float = 30.0, interval: float = 0.3) -> None:
    """Block until an HTTP endpoint answers 2xx. Used by the SUT fixture and CI."""
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code < 400:
                return
        except httpx.HTTPError as exc:  # noqa: PERF203
            last = exc
        time.sleep(interval)
    raise TimeoutError(f"{url} did not become healthy within {timeout}s (last error: {last})")
