"""Native app tests (Appium).

These skip automatically unless an Appium server is reachable — see the root
conftest. Point `QA_APP_PATH` at your .apk/.ipa and adjust the locators in
`framework/mobile/screens.py` to run them against a real app.

What is worth automating on a real device, in priority order:

  1. Things that only exist on device: permissions dialogs, biometrics, push,
     deep links, background/foreground, network loss, rotation, back button.
  2. The one or two critical revenue journeys.
  3. Platform-specific UI you cannot emulate.

What is NOT worth automating on device: business-rule permutations, validation
tables, error messages. Push those to the services layer — they run in
milliseconds there and take minutes here.
"""

from __future__ import annotations

import pytest

from framework.data.factories import persona
from framework.mobile.screens import CartScreen, LoginScreen, ProductsScreen
from framework.utils.assertions import approx_money, soft

pytestmark = pytest.mark.mobile_native


@pytest.mark.smoke
def test_user_can_log_in(login_screen: LoginScreen) -> None:
    user = persona("standard")

    products = login_screen.login(user.username, user.password)

    assert products.is_displayed(ProductsScreen.root), "Products screen did not appear after login"


def test_invalid_credentials_show_an_error(login_screen: LoginScreen) -> None:
    login_screen.login_expecting_failure("alice", "definitely-wrong")

    assert "invalid" in login_screen.error_text.lower()


@pytest.mark.smoke
def test_add_to_cart_and_checkout(products_screen: ProductsScreen) -> None:
    name = products_screen.product_names[0]

    products_screen.add_to_cart(name)

    soft(products_screen.cart_count == 1, f"Badge shows {products_screen.cart_count}, expected 1")
    cart = products_screen.open_cart()
    soft(not cart.is_empty, "Cart screen reports empty after adding an item")

    cart.checkout()

    assert "confirmed" in cart.confirmation_text.lower()


def test_scrolling_reveals_products_below_the_fold(products_screen: ProductsScreen) -> None:
    """`scroll_to_text` uses UiScrollable on Android — a native, fast scroll.
    Hand-rolled swipe loops are the slow, flaky alternative."""
    last_product = "Flux Webcam"

    element = products_screen.scroll_to_text(last_product)

    assert element.is_displayed()


def test_app_survives_backgrounding(products_screen: ProductsScreen) -> None:
    """Backgrounding is where mobile apps lose state, drop sockets and crash.
    This is a device-only scenario and one of the highest-value mobile tests."""
    name = products_screen.product_names[0]
    products_screen.add_to_cart(name)

    products_screen.driver.background_app(5)

    assert products_screen.cart_count == 1, "Cart contents were lost when the app was backgrounded"


def test_rotation_preserves_state(products_screen: ProductsScreen) -> None:
    """On Android, rotation destroys and recreates the Activity. Anything not
    saved in onSaveInstanceState is gone — a defect class unique to mobile."""
    name = products_screen.product_names[0]
    products_screen.add_to_cart(name)

    products_screen.driver.orientation = "LANDSCAPE"
    try:
        assert products_screen.cart_count == 1, "Cart was cleared by rotation"
    finally:
        products_screen.driver.orientation = "PORTRAIT"


def test_back_navigation_returns_to_the_previous_screen(products_screen: ProductsScreen) -> None:
    """Android's hardware back button has no web equivalent and is a reliable
    source of broken navigation stacks."""
    cart = products_screen.open_cart()
    assert cart.is_displayed(CartScreen.root)

    cart.driver.back()

    assert products_screen.is_displayed(ProductsScreen.root), "Back did not return to products"


@pytest.mark.slow
def test_app_handles_loss_of_connectivity(products_screen: ProductsScreen) -> None:
    """Airplane-mode simulation. `set_network_connection` is Android-only; the
    skip is explicit rather than a silent pass."""
    if not products_screen.is_android:
        pytest.skip("Network condition control is Android-only via UiAutomator2")

    driver = products_screen.driver
    driver.set_network_connection(1)  # 1 = airplane mode
    try:
        products_screen.search("aurora")
        assert products_screen.is_displayed(
            (products_screen.root[0], products_screen.root[1]), timeout=5
        ), "App crashed or showed a blank screen when offline"
    finally:
        driver.set_network_connection(6)  # 6 = wifi + data


def test_totals_match_the_backend(products_screen: ProductsScreen, base_url: str) -> None:
    """Cross-layer verification on mobile: drive the UI, verify at the API.

    The device shows what the user sees; the API shows what the business
    recorded. A mismatch between them is the bug worth finding.
    """
    from framework.api.shop import ShopApi
    from framework.http.client import ApiClient

    user = persona("standard")
    name = products_screen.product_names[0]
    products_screen.add_to_cart(name)
    ui_total = products_screen.open_cart().total

    with ApiClient(base_url=base_url) as client:
        api_total = ShopApi(client).login_as(user.username, user.password).cart.get().total

    approx_money(ui_total, api_total)
