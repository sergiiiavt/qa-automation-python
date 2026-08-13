"""Cart and checkout — business-flow tests at the API layer.

These are the tests that *should* carry most of your regression coverage. They
exercise the same rules the UI enforces, at ~1% of the cost and ~0% of the flake.
Reserve the UI suite for what only the UI can prove.
"""

from __future__ import annotations

import pytest

from framework.api.models import Product
from framework.api.shop import ShopApi
from framework.utils.assertions import approx_money, soft


@pytest.mark.smoke
def test_add_item_to_empty_cart(shop_as_user: ShopApi) -> None:
    product = shop_as_user.products.first_in_stock()

    cart = shop_as_user.cart.add_item(product.id, quantity=2)

    line = cart.line_for(product.id)
    assert line is not None, f"Product {product.id} missing from cart {cart.items}"
    assert line.quantity == 2
    approx_money(line.line_total, product.price * 2)
    approx_money(cart.total, product.price * 2)


def test_adding_same_product_twice_increments_quantity(shop_as_user: ShopApi) -> None:
    """A behaviour worth pinning down: does the API *merge* lines or *append*
    duplicates? Both are defensible designs; only one matches the spec, and an
    unpinned choice will silently flip during a refactor."""
    product = shop_as_user.products.first_in_stock()

    shop_as_user.cart.add_item(product.id, 1)
    cart = shop_as_user.cart.add_item(product.id, 2)

    assert len(cart.items) == 1, "Duplicate lines created instead of merging"
    assert cart.line_for(product.id).quantity == 3


def test_cart_total_is_sum_of_line_totals(shop_as_user: ShopApi) -> None:
    products = [p for p in shop_as_user.products.list(in_stock=True)][:3]
    assert len(products) >= 2, "Need at least 2 in-stock products for this test"

    for index, product in enumerate(products, start=1):
        shop_as_user.cart.add_item(product.id, index)

    cart = shop_as_user.cart.get()
    expected = sum(p.price * i for i, p in enumerate(products, start=1))

    approx_money(cart.total, expected)
    assert cart.currency == "USD"


def test_remove_item_updates_total(cart_with_item: tuple[ShopApi, Product]) -> None:
    shop, product = cart_with_item

    cart = shop.cart.remove_item(product.id)

    assert cart.line_for(product.id) is None
    approx_money(cart.total, 0.0)


def test_removing_a_product_that_is_not_in_the_cart_is_idempotent(shop_as_user: ShopApi) -> None:
    """DELETE should be idempotent — deleting twice must not 404 or 500."""
    product = shop_as_user.products.first_in_stock()
    shop_as_user.cart.add_item(product.id, 1)

    shop_as_user.cart.remove_item(product.id)
    cart = shop_as_user.cart.remove_item(product.id)   # second delete

    assert cart.items == []


def test_cannot_add_out_of_stock_product(shop_as_user: ShopApi) -> None:
    product = shop_as_user.products.first_out_of_stock()

    response = shop_as_user.cart.add_item_raw(product.id, 1)

    assert response.status_code == 409
    assert "out of stock" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    ("quantity", "expected_status", "case"),
    [
        (1, 201, "minimum valid"),
        (99, 201, "maximum valid"),
        (0, 422, "below minimum"),
        (-1, 422, "negative"),
        (100, 422, "above maximum"),
        (1.5, 422, "non-integer"),
        ("2", 201, "numeric string — coerced by the API"),
    ],
)
def test_quantity_boundaries(
    shop_as_user: ShopApi, quantity: object, expected_status: int, case: str
) -> None:
    """Boundary-value analysis, done properly: min, min-1, max, max+1, and the
    type boundary. Three of these five rows have caught real defects in the
    author's experience; the middle-of-range value has caught none."""
    product = shop_as_user.products.first_in_stock()

    response = shop_as_user.cart.add_item_raw(product.id, quantity)

    assert response.status_code == expected_status, f"[{case}] body: {response.text[:300]}"


@pytest.mark.parametrize("product_id", [999999, 0, -1, "abc"])
def test_adding_unknown_product_is_rejected(shop_as_user: ShopApi, product_id: object) -> None:
    response = shop_as_user.cart.add_item_raw(product_id, 1)

    assert response.status_code in (404, 422), f"got {response.status_code}: {response.text[:200]}"


@pytest.mark.smoke
def test_checkout_creates_order_and_empties_cart(cart_with_item: tuple[ShopApi, Product]) -> None:
    shop, product = cart_with_item
    cart_before = shop.cart.get()

    order = shop.orders.create()

    soft(order.status == "confirmed", f"Unexpected order status: {order.status}")
    soft(order.id.startswith("ord_"), f"Unexpected order id format: {order.id}")
    approx_money(order.total, cart_before.total)
    assert shop.cart.get().items == [], "Cart should be emptied after checkout"


def test_order_is_retrievable_after_creation(cart_with_item: tuple[ShopApi, Product]) -> None:
    shop, _ = cart_with_item

    created = shop.orders.create()
    fetched = shop.orders.get(created.id)

    assert fetched == created, "GET /orders/{id} does not round-trip the created order"


def test_checkout_with_empty_cart_is_rejected(shop_as_user: ShopApi) -> None:
    response = shop_as_user.orders.create_raw()

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.xfail(
    reason="KNOWN DEFECT SHOP-114: GET /api/orders/{id} does not check ownership",
    strict=True,
)
def test_order_belongs_to_its_owner(
    cart_with_item: tuple[ShopApi, Product], shop_as_second_user: ShopApi
) -> None:
    """BOLA / IDOR check — OWASP API Security's #1 risk.

    Every resource-by-id endpoint deserves this test. It is three lines and it
    finds the single most commonly exploited API vulnerability.

    This one currently FAILS against the SUT, on purpose. Note how the defect is
    handled: `xfail(strict=True)` with a ticket id. The build stays green *and*
    the moment someone fixes SHOP-114 the xpass turns the build red, forcing the
    marker to be removed. A commented-out test or a `skip` would have silently
    rotted instead.
    """
    shop, _ = cart_with_item
    order = shop.orders.create()

    response = shop_as_second_user.client.get(f"/api/orders/{order.id}")

    assert response.status_code in (403, 404), (
        f"Bob read Alice's order {order.id} (status {response.status_code}) — "
        f"broken object-level authorization"
    )
