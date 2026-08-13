"""Fixtures for the services layer.

Scope discipline is the main lesson here:

  session  — expensive, immutable things (a client, a schema, an admin token)
  function — anything a test could dirty

Getting this wrong in either direction hurts: too broad and tests leak state into
each other; too narrow and you re-authenticate 400 times and the suite crawls.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from framework.api.shop import ShopApi
from framework.http.client import ApiClient


@pytest.fixture(scope="session")
def openapi_schema(base_url: str) -> dict:
    """The SUT's contract, fetched once. Used by contract & schema tests."""
    return httpx.get(f"{base_url}/openapi.json", timeout=10).json()


@pytest.fixture
def api_client(base_url: str) -> Iterator[ApiClient]:
    """Anonymous client. Function-scoped: auth state is mutable, so sharing one
    client across tests would leak a token from an authenticated test into an
    unauthenticated one — a genuinely nasty, order-dependent failure."""
    with ApiClient(base_url=base_url) as client:
        yield client


@pytest.fixture
def shop(api_client: ApiClient) -> ShopApi:
    """Unauthenticated facade."""
    return ShopApi(api_client)


@pytest.fixture
def auth_token(base_url: str, worker_account: tuple[str, str]) -> str:
    """A fresh token. Separate from `shop` so a test can hand the token to a
    *second* client and prove two sessions don't interfere."""
    with ApiClient(base_url=base_url) as client:
        username, password = worker_account
        return ShopApi(client).auth.login(username, password).token


@pytest.fixture
def shop_as_user(shop: ShopApi, worker_account: tuple[str, str]) -> Iterator[ShopApi]:
    """Logged-in facade with a guaranteed-empty cart, both before and after.

    Uses this worker's own account (see `worker_account` in the root conftest),
    which is what makes `-n auto` safe.

    Cleaning up *before* as well as after is deliberate: the previous run may
    have crashed mid-test, and a fixture that only cleans on teardown leaves the
    next run to inherit the mess.
    """
    username, password = worker_account
    shop.login_as(username, password)
    shop.cart.clear()
    yield shop
    shop.cart.clear()


@pytest.fixture
def shop_as_second_user(base_url: str) -> Iterator[ShopApi]:
    """A second, freshly-registered account — for isolation and BOLA tests.

    Registered per test rather than per worker: isolation tests are exactly the
    ones you do not want sharing state with anything.
    """
    import httpx

    from framework.data.factories import unique_username

    username, password = unique_username("other"), "Str0ng!Passw0rd"
    httpx.post(
        f"{base_url}/api/auth/register",
        json={"username": username, "password": password},
        timeout=10,
    ).raise_for_status()

    with ApiClient(base_url=base_url) as client:
        yield ShopApi(client).login_as(username, password)


@pytest.fixture
def cart_with_item(shop_as_user: ShopApi):
    """Composed fixture: a logged-in user whose cart already holds one product.

    Composition over duplication — five tests need this precondition; write it
    once and let pytest's dependency graph assemble it.
    """
    product = shop_as_user.products.first_in_stock()
    shop_as_user.cart.add_item(product.id, 1)
    return shop_as_user, product


# NOTE: an autouse `POST /api/testing/reset` fixture used to live here. It was
# removed on purpose. Under `-n 4` each worker ran it at session start, wiping
# the *other* workers' sessions mid-run. A global reset is fundamentally
# incompatible with parallel execution — per-test/per-worker data isolation
# (see `worker_account`) is the mechanism that scales. Keep a global reset only
# as a manual, pre-run step:
#     curl -X POST http://127.0.0.1:8000/api/testing/reset
