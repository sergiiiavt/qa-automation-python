"""Authentication: the canonical positive/negative/boundary trio.

Read this file for *test design*, not just syntax:
  - one behaviour per test, named after the behaviour;
  - negative cases are parametrized as a table, not copy-pasted;
  - assertions check the contract (status, shape, message), not implementation.
"""

from __future__ import annotations

import pytest

from framework.api.models import LoginResponse
from framework.api.shop import ShopApi
from framework.data.factories import persona
from framework.utils.assertions import soft


@pytest.mark.smoke
def test_login_with_valid_credentials_returns_token(shop: ShopApi) -> None:
    user = persona("standard")

    result = shop.auth.login(user.username, user.password)

    # model_validate already enforced the schema; assert on the *values* that
    # carry meaning for the caller.
    assert isinstance(result, LoginResponse)
    assert result.username == user.username
    assert result.expires_in == 3600
    assert len(result.token) >= 16, "Token is suspiciously short — check entropy"


def test_tokens_are_unique_per_login(shop: ShopApi) -> None:
    """A reused token across logins is a real security defect, and a trivial
    test to write. Cheap tests for expensive bugs are the best ratio in QA."""
    user = persona("standard")

    first = shop.auth.login(user.username, user.password).token
    second = shop.auth.login(user.username, user.password).token

    assert first != second


@pytest.mark.parametrize(
    ("username", "password", "case"),
    [
        ("alice", "wrong-password", "wrong password"),
        ("nosuchuser", "wonderland", "unknown user"),
        ("ALICE", "wonderland", "username case mismatch"),
        ("alice ", "wonderland", "trailing whitespace in username"),
        ("alice", "wonderland ", "trailing whitespace in password"),
    ],
    ids=lambda v: v if isinstance(v, str) and " " in v else None,
)
def test_login_rejects_bad_credentials(shop: ShopApi, username: str, password: str, case: str) -> None:
    """One table, five behaviours. Note the ids: a failing run says
    `test_login_rejects_bad_credentials[username case mismatch]`, so triage
    starts before you open the log."""
    response = shop.auth.login_raw(username, password)

    assert response.status_code == 401, f"[{case}] expected 401"
    # Error text must not disclose which half was wrong — user enumeration risk.
    # Split into two assertions rather than `a and b`: a combined assertion tells
    # you it failed but not which half. Two assertions name the actual leak.
    body = response.json()["detail"].lower()
    assert "password" not in body, f"[{case}] error message names the password: {body!r}"
    assert "username" not in body, f"[{case}] error message names the username: {body!r}"


@pytest.mark.parametrize(
    ("payload", "case"),
    [
        ({}, "empty body"),
        ({"username": "alice"}, "missing password"),
        ({"password": "wonderland"}, "missing username"),
        ({"username": "", "password": ""}, "empty strings"),
        ({"username": "a" * 500, "password": "x"}, "oversized username"),
        ({"username": 12345, "password": True}, "wrong types"),
    ],
)
def test_login_rejects_malformed_payloads(shop: ShopApi, payload: dict, case: str) -> None:
    """Validation errors must be 4xx and must never be 5xx.

    A 500 on bad input means the input reached code that didn't expect it — the
    exact shape of bug that turns into a security finding later.
    """
    response = shop.client.post("/api/auth/login", json=payload)

    assert 400 <= response.status_code < 500, (
        f"[{case}] expected client error, got {response.status_code} — "
        f"the server crashed on malformed input"
    )


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "wonderland",                    # no scheme
        "Basic YWxpY2U6d29uZGVy",        # wrong scheme
        "Bearer",                        # scheme with no token
        "Bearer not-a-real-token",
        "bearer lowercase-scheme-valid-token-shape",
    ],
)
def test_protected_endpoint_requires_valid_bearer_token(shop: ShopApi, header: str | None) -> None:
    headers = {} if header is None else {"Authorization": header}

    response = shop.client.get("/api/cart", headers=headers)

    assert response.status_code == 401


def test_two_users_have_isolated_carts(shop_as_user: ShopApi, shop_as_second_user: ShopApi) -> None:
    """Multi-tenancy isolation — the bug class that makes headlines.

    Two fixtures, two real sessions. This is why `api_client` is function-scoped:
    a shared client could not express this scenario at all.
    """
    product = shop_as_user.products.first_in_stock()

    shop_as_user.cart.add_item(product.id, 3)

    alice_cart = shop_as_user.cart.get()
    bob_cart = shop_as_second_user.cart.get()

    soft(alice_cart.item_count == 3, f"Alice should see 3 items, saw {alice_cart.item_count}")
    soft(bob_cart.item_count == 0, f"Bob's cart leaked Alice's items: {bob_cart.items}")
