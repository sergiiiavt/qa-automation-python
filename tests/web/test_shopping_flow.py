"""End-to-end shopping flows.

Notice how few of these there are, and how much they cover. The API suite proves
the *rules* (totals, boundaries, permissions); these prove the *wiring* — that
the UI sends what the API expects and renders what it gets back. That split is
what keeps a UI suite from taking 40 minutes.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.api.shop import ShopApi
from framework.utils.assertions import approx_money, soft
from framework.web.pages import App


@pytest.mark.smoke
def test_product_grid_renders_the_catalogue(app: App) -> None:
    products = app.products.open()

    cards = products.cards

    assert len(cards) >= 5
    first = cards[0]
    soft(bool(first.name), "Product card has no name")
    soft(first.price > 0, f"Product '{first.name}' has a non-positive price")
    soft(first.category != "", "Product card has no category")


def test_ui_and_api_agree_on_the_catalogue(app: App, api_seed: ShopApi) -> None:
    """Cross-layer consistency — my favourite kind of test.

    The UI must render exactly what the API serves. This catches client-side
    filtering, pagination and caching bugs that neither layer finds alone.
    """
    products = app.products.open()

    ui_names = sorted(products.product_names)
    api_names = sorted(p.name for p in api_seed.products.list())

    assert ui_names == api_names


def test_search_filters_the_grid(app: App) -> None:
    products = app.products.open()

    products.search("aurora")

    names = products.product_names
    assert names, "Search returned nothing"
    assert all("aurora" in name.lower() for name in names)
    expect(products.status).to_contain_text("product(s)")


def test_search_with_no_results_shows_zero_and_no_error(app: App) -> None:
    products = app.products.open()

    products.search("zzz-nothing-here")

    assert products.testid("product-card").count() == 0
    expect(products.status).to_have_text("0 product(s)")


def test_category_filter(app: App) -> None:
    products = app.products.open()

    products.filter_by_category("audio")

    assert products.product_names
    assert all(card.category == "audio" for card in products.cards)


def test_out_of_stock_products_cannot_be_added(app_as_user: App) -> None:
    products = app_as_user.products.open()

    out_of_stock = next(c for c in products.cards if not c.in_stock)

    expect(out_of_stock.root.get_by_test_id("add-to-cart")).to_be_disabled()


@pytest.mark.smoke
def test_add_to_cart_updates_the_badge(app_as_user: App) -> None:
    products = app_as_user.products.open()
    card = products.cards[0]

    card.add_to_cart()

    expect(products.testid("cart-count")).to_have_text("1")
    expect(products.status).to_contain_text("added to cart")


def test_anonymous_user_is_sent_to_login_when_adding_to_cart(app: App) -> None:
    products = app.products.open()

    products.cards[0].add_to_cart()

    expect(products.page).to_have_url(f"{products.base_url}/login")


@pytest.mark.smoke
@pytest.mark.regression
def test_complete_purchase_journey(app_as_user: App, api_seed: ShopApi) -> None:
    """The one true end-to-end test: browse -> add -> cart -> checkout.

    A suite needs a handful of these and no more. They are the most expensive
    tests you own and the first to go flaky; every additional one buys less
    coverage than an API test costing 1% as much.
    """
    api_seed.cart.clear()
    products = app_as_user.products.open()
    card = products.cards[0]
    name, price = card.name, card.price

    card.add_to_cart()
    expect(products.testid("cart-count")).to_have_text("1")

    cart = app_as_user.cart.open()
    expect(cart.row_for(name)).to_be_visible()
    approx_money(cart.total, price)

    cart.checkout()

    expect(cart.status).to_contain_text("confirmed")
    assert cart.is_empty, "Cart should be empty after a successful order"
    # And the truth of it, checked at the source rather than on screen:
    assert api_seed.cart.get().items == []


def test_removing_an_item_updates_the_total(app_as_user: App, api_seed: ShopApi) -> None:
    """Precondition via API, verification via UI — the pattern to default to."""
    api_seed.cart.clear()
    product = api_seed.products.first_in_stock()
    api_seed.cart.add_item(product.id, 2)

    cart = app_as_user.cart.open()
    approx_money(cart.total, product.price * 2)

    cart.remove(product.name)

    approx_money(cart.total, 0.0)
    assert cart.is_empty


def test_checkout_button_is_disabled_for_an_empty_cart(app_as_user: App, api_seed: ShopApi) -> None:
    api_seed.cart.clear()

    cart = app_as_user.cart.open()

    expect(cart.testid("checkout")).to_be_disabled()
    assert cart.is_empty


def test_cart_survives_a_page_reload(app_as_user: App, api_seed: ShopApi) -> None:
    api_seed.cart.clear()
    product = api_seed.products.first_in_stock()
    api_seed.cart.add_item(product.id, 1)

    cart = app_as_user.cart.open()
    cart.reload()

    expect(cart.row_for(product.name)).to_be_visible()


@pytest.mark.regression
def test_api_failure_is_surfaced_to_the_user(app_as_user: App) -> None:
    """Fault injection via route interception.

    Playwright can intercept network traffic, which lets a UI test cover the
    error paths QA normally can't reach: 500s, timeouts, empty responses.
    These branches are almost never manually tested and almost always broken.
    """
    page = app_as_user.page
    page.route(
        "**/api/cart/items",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body='{"detail":"Internal error"}'
        ),
    )

    products = app_as_user.products.open()
    products.cards[0].add_to_cart()

    # The requirement: fail visibly, never silently.
    expect(products.status).to_contain_text("Internal error")
    expect(products.status).to_have_class("error")


@pytest.mark.regression
def test_slow_api_does_not_break_the_page(app_as_user: App) -> None:
    """Latency injection. Catches missing loading states and premature asserts
    in the app's own code."""
    page = app_as_user.page

    def _delay(route):
        import time

        time.sleep(1.5)
        route.continue_()

    page.route("**/api/products*", _delay)

    products = app_as_user.products.open()

    expect(products.testid("product-grid")).to_have_attribute("data-loaded", "true", timeout=15_000)
    assert products.product_names
