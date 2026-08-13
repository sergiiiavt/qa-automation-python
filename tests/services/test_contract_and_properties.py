"""Contract testing and property-based testing.

This is where a suite stops being a list of examples someone thought of, and
starts being a machine that thinks of examples for you.

Three techniques, three different jobs:

  1. **Schemathesis** — reads the OpenAPI spec and generates requests that are
     valid *per the spec*, then checks the responses are valid per the spec.
     Finds: undocumented 500s, responses that don't match declared schemas,
     missing status codes, header/content-type violations.

  2. **Hypothesis** — you state an invariant ("the cart total always equals the
     sum of its lines"), it hunts for a counterexample and *shrinks* it to the
     minimal failing input. Finds: arithmetic and state-machine bugs.

  3. **respx** — mocks httpx so the *framework itself* can be unit-tested.
     A framework nobody tests is a framework nobody can refactor.
"""

from __future__ import annotations

import httpx
import pytest
import respx
import schemathesis
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from framework.api.shop import ShopApi
from framework.http.client import ApiClient, ApiError
from framework.utils.assertions import approx_money
from sut.app import app as sut_app

# Loading the schema from the ASGI app (not a URL) means collection never
# depends on a running server — schema-driven tests stay collectable offline.
schema = schemathesis.openapi.from_asgi("/openapi.json", sut_app)


@pytest.mark.contract
@schema.parametrize()
@hypothesis_settings(
    max_examples=15,  # keep CI honest; raise to 200 for a nightly run
    deadline=None,  # server latency is not the property under test
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
        # `GET /api/cart` and `POST /api/orders` take no parameters and no body,
        # so the only thing Hypothesis can vary is headers. It runs out of
        # distinct examples, filters the duplicates, and trips `filter_too_much`
        # — intermittently, because it depends on the random seed. That is a
        # property of the generator meeting a tiny input space, not a signal
        # about the API, so it is suppressed rather than worked around.
        HealthCheck.filter_too_much,
    ],
)
def test_api_conforms_to_its_openapi_spec(case: schemathesis.Case) -> None:
    """One generated test per operation in the spec.

    `call_and_validate` runs the built-in checks: not_a_server_error,
    status_code_conformance, content_type_conformance, response_schema_conformance,
    positive_data_acceptance. A failure prints a curl command that reproduces it —
    paste that straight into a ticket.

    ### Triage log (read this — it is the real lesson)

    Three findings came out of the first runs of this single test:

      1. *Undocumented status code 400/401* — REAL. The service returns them;
         the spec never mentioned them. Fixed by documenting them (sut/app.py).
      2. *Response schema mismatch on 422* — REAL, and self-inflicted by the fix
         for (1): we declared `detail: string` while FastAPI returns a list of
         error objects. Fixed by removing the wrong override.
      3. *`positive_data_acceptance` on `?in_stock=null`* — NOT a product bug.
         An optional query parameter is `boolean | null` in the schema, but a
         URL query string has no way to express JSON `null`; the generator sends
         the literal text "null" and the server correctly rejects it. This is a
         limitation of OpenAPI's expressiveness, not a defect.

    Finding (3) is excluded below, *with the reason recorded next to the code*.
    Excluding a check without writing down why is how contract testing decays
    into a permanently-yellow job everyone ignores.

    A fourth finding appeared later, and only under `pytest -n 4`: an
    intermittent `FailedHealthCheck: Too many generated examples are filtered
    out`. Also not a product bug — see the `filter_too_much` note on the
    settings below. Two lessons in one test: generated-testing tools produce
    findings about *themselves* as well as about the system, and a flake that
    only appears in parallel is still a flake that must be diagnosed rather
    than retried.
    """
    from schemathesis.specs.openapi.checks import positive_data_acceptance

    case.call_and_validate(excluded_checks=[positive_data_acceptance])


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------
@pytest.mark.slow
@given(quantities=st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=4))
@hypothesis_settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_cart_total_always_equals_sum_of_lines(
    shop_as_user: ShopApi, quantities: list[int]
) -> None:
    """The invariant, not the example.

    Note the health-check suppression: `shop_as_user` is function-scoped, so
    Hypothesis reuses it across examples. That is acceptable *only* because the
    test resets the cart itself. Read that as the general rule — if you suppress
    `function_scoped_fixture`, you have taken responsibility for isolation.
    """
    shop_as_user.cart.clear()
    products = shop_as_user.products.list(in_stock=True)[: len(quantities)]

    expected = 0.0
    for product, quantity in zip(products, quantities, strict=False):
        shop_as_user.cart.add_item(product.id, quantity)
        expected += product.price * quantity

    cart = shop_as_user.cart.get()

    approx_money(cart.total, expected)
    approx_money(sum(line.line_total for line in cart.items), cart.total)


@pytest.mark.slow
@given(
    term=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),  # no lone surrogates
        min_size=0,
        max_size=40,
    )
)
@hypothesis_settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_search_never_crashes_and_never_returns_unrelated_items(shop: ShopApi, term: str) -> None:
    """Fuzzing a search box: unicode, emoji, SQL fragments, control characters.

    Two properties, both cheap:
      * the endpoint answers 2xx for any string (no 500s);
      * every result actually contains the term (no filter bypass).
    """
    response = shop.client.get("/api/products", params={"q": term})

    assert response.status_code == 200, f"Search crashed on {term!r}: {response.status_code}"
    for product in response.json():
        assert term.lower() in product["name"].lower(), (
            f"Search for {term!r} returned unrelated product {product['name']!r}"
        )


@pytest.mark.parametrize(
    "payload",
    ["' OR '1'='1", "<script>alert(1)</script>", "../../etc/passwd", "%00", "{{7*7}}"],
)
def test_search_rejects_injection_payloads_safely(shop: ShopApi, payload: str) -> None:
    """Injection strings should be *data*, not code.

    Deliberately `parametrize`, not `@given(st.sampled_from(...))`: when the
    inputs are a fixed, hand-curated list, parametrize gives one test id per
    payload, works with function-scoped fixtures, and doesn't pay Hypothesis's
    machinery cost. Reach for Hypothesis when you want inputs you did *not*
    think of — see the fuzz test above.
    """
    response = shop.client.get("/api/products", params={"q": payload})

    assert response.status_code == 200
    assert response.json() == [], f"Injection payload {payload!r} matched products"
    assert "49" not in response.text or "7*7" not in payload, (
        "Template injection: {{7*7}} evaluated"
    )


# ---------------------------------------------------------------------------
# Testing the framework itself — respx mocks the transport layer.
# ---------------------------------------------------------------------------
@respx.mock
def test_api_client_retries_transient_5xx_on_idempotent_requests() -> None:
    """Proves the retry policy without needing a flaky server.

    Every piece of "clever" framework logic — retries, backoff, token refresh —
    needs a test like this, or it is untrustworthy exactly when it matters.
    """
    route = respx.get("http://sut.test/api/products").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json=[]),
        ]
    )

    with ApiClient(base_url="http://sut.test", retries=2) as client:
        response = client.get("/api/products", expect=200)

    assert response.status_code == 200
    assert route.call_count == 3, "Retry policy did not fire the expected number of times"


@respx.mock
def test_api_client_does_not_retry_post() -> None:
    """A retried POST can create two orders. This test is the guardrail that
    stops a well-meaning future change from making POST retryable."""
    route = respx.post("http://sut.test/api/orders").mock(return_value=httpx.Response(503))

    with ApiClient(base_url="http://sut.test", retries=3) as client:
        response = client.post("/api/orders")

    assert response.status_code == 503
    assert route.call_count == 1, "POST must never be retried automatically"


@respx.mock
def test_api_error_message_includes_request_and_response_detail() -> None:
    """Failure *messages* are a feature. Test them like one."""
    respx.get("http://sut.test/api/cart").mock(
        return_value=httpx.Response(403, json={"detail": "Forbidden"})
    )

    with ApiClient(base_url="http://sut.test") as client, pytest.raises(ApiError) as exc_info:
        client.get("/api/cart", expect=200)

    message = str(exc_info.value)
    assert "GET" in message, "Failure message omits the HTTP method"
    assert "403" in message, "Failure message omits the actual status code"
    assert "Forbidden" in message, "Failure message omits the response body"
