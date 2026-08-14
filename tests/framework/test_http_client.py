"""Regression test for the retry-exhaustion bug in framework/http/client.py.

See tests/services/test_contract_and_properties.py for the framework's other
respx-based ApiClient tests (retry-on-transient-5xx, POST is never retried,
error-message content). This one covers the exhausted-retries path, which
those don't: previously `_send_with_retries` caught the exhausted
`RetryableStatus` and fired one more raw request instead of returning the
response tenacity already had, so the true request count was `attempts + 1`.
"""

from __future__ import annotations

import httpx
import respx

from framework.http.client import ApiClient


@respx.mock
def test_exhausted_retries_do_not_send_one_extra_request() -> None:
    route = respx.get("http://sut.test/api/products").mock(return_value=httpx.Response(503))

    with ApiClient(base_url="http://sut.test", retries=2) as client:
        response = client.get("/api/products")

    assert response.status_code == 503
    assert route.call_count == 3, (
        "retries=2 means 3 total attempts (1 + 2 retries); a 4th call means the "
        "exhausted-retry path is still sending an extra request after tenacity gives up"
    )


@respx.mock
def test_exhausted_retries_return_the_real_last_response_body() -> None:
    route = respx.get("http://sut.test/api/products").mock(
        return_value=httpx.Response(503, json={"detail": "still down"})
    )

    with ApiClient(base_url="http://sut.test", retries=1) as client:
        response = client.get("/api/products")

    assert response.json() == {"detail": "still down"}
    assert route.call_count == 2
