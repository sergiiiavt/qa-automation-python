"""Mobile web — emulated devices.

**The pragmatic position of this course:** most mobile-web defects are layout,
touch-target and viewport defects, and Playwright's device emulation finds them
in seconds without a device farm. Emulation gives you the real mobile user-agent,
device-scale factor, touch flags and viewport — but it is still desktop Chromium
rendering, so it cannot find genuine engine bugs (iOS Safari quirks, real
scroll/momentum behaviour, on-device font fallback).

The strategy that actually works in industry:

    every commit    -> emulated mobile web (Playwright), 2-3 min
    nightly / release -> the same tests on real devices via Appium (tests/mobile)

Same Page Objects across both. If a device suite needs its own Page Objects,
the abstraction was wrong.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page, Playwright, expect

from framework.api.shop import ShopApi
from framework.web.pages import App

pytestmark = pytest.mark.mobile_web

# Playwright ships descriptors for real hardware; use them instead of guessing
# viewport numbers. Names come from playwright.devices.
DEVICES = ["iPhone 15", "Pixel 7", "Galaxy S9+", "iPad (gen 7)"]


@pytest.fixture(params=DEVICES, ids=DEVICES)
def mobile_page(
    request: pytest.FixtureRequest,
    playwright: Playwright,
    browser: Browser,
    base_url: str,
    storage_state: str,
) -> Page:
    """One authenticated page per emulated device.

    Parametrizing the *fixture* rather than every test means adding a device to
    the matrix is a one-line change that instantly covers the whole file.
    """
    descriptor = playwright.devices[request.param]
    context = browser.new_context(**descriptor, base_url=base_url, storage_state=storage_state)
    page = context.new_page()
    yield page
    context.close()


def test_layout_collapses_to_a_mobile_nav(mobile_page: Page) -> None:
    """The single most valuable mobile-web assertion: does the responsive
    breakpoint actually fire on real device widths?"""
    products = App(mobile_page).products.open()
    width = mobile_page.viewport_size["width"]

    if width <= 640:
        expect(products.testid("menu-toggle")).to_be_visible()
        expect(products.testid("main-nav")).to_be_hidden()
    else:  # tablets keep the desktop nav
        expect(products.testid("main-nav")).to_be_visible()


def test_mobile_nav_opens_and_is_announced(mobile_page: Page) -> None:
    products = App(mobile_page).products.open()
    if mobile_page.viewport_size["width"] > 640:
        pytest.skip("Tablet keeps the desktop navigation")

    toggle = products.testid("menu-toggle")
    expect(toggle).to_have_attribute("aria-expanded", "false")

    products.open_nav()

    expect(products.testid("main-nav")).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "true")


def test_no_horizontal_scrolling(mobile_page: Page) -> None:
    """Horizontal overflow is *the* mobile bug: an element wider than the
    viewport, usually a table or an unbroken string. Cheap to detect, and
    nobody notices it in a desktop browser."""
    App(mobile_page).products.open()

    overflow = mobile_page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )

    assert overflow <= 1, f"Page scrolls horizontally by {overflow}px on this device"


def test_touch_targets_meet_the_minimum_size(mobile_page: Page) -> None:
    """WCAG 2.2 (2.5.8) asks for 24x24 CSS px; iOS HIG and Material both say 44-48.
    This asserts the stricter, humane 44px on interactive controls."""
    products = App(mobile_page).products.open()
    if mobile_page.viewport_size["width"] > 640:
        pytest.skip("Desktop-width layout — touch sizing does not apply")

    too_small: list[str] = []
    for selector in [
        "[data-testid=menu-toggle]",
        "[data-testid=add-to-cart]",
        "[data-testid=apply-filters]",
    ]:
        box = products.page.locator(selector).first.bounding_box()
        if box and (box["width"] < 44 or box["height"] < 44):
            too_small.append(f"{selector}: {box['width']:.0f}x{box['height']:.0f}")

    assert not too_small, f"Touch targets below 44x44 CSS px: {too_small}"


def test_device_reports_a_mobile_user_agent(mobile_page: Page) -> None:
    App(mobile_page).products.open()

    ua = mobile_page.evaluate("() => navigator.userAgent")
    has_touch = mobile_page.evaluate(
        "() => 'ontouchstart' in window || navigator.maxTouchPoints > 0"
    )

    assert any(token in ua for token in ("iPhone", "Android", "iPad")), ua
    assert has_touch, "Device emulation did not enable touch — descriptor may be wrong"


def test_can_complete_a_purchase_on_a_phone(mobile_page: Page, api_seed: ShopApi) -> None:
    """The mobile journey, tap by tap. Same Page Objects as the desktop test —
    the only mobile-specific step is opening the nav."""
    api_seed.cart.clear()
    app = App(mobile_page)

    products = app.products.open()
    card = products.cards[0]
    name = card.name
    card.add_to_cart()
    expect(products.testid("cart-count")).to_have_text("1")

    products.go_to_cart()
    cart = app.cart
    cart.wait_until_ready()
    expect(cart.row_for(name)).to_be_visible()

    cart.checkout()

    expect(cart.status).to_contain_text("confirmed")


def test_content_is_readable_without_zooming(mobile_page: Page) -> None:
    """Font size below 12px on a phone is a real usability defect and a common
    consequence of reusing desktop CSS."""
    products = App(mobile_page).products.open()
    if mobile_page.viewport_size["width"] > 640:
        pytest.skip("Desktop-width layout")

    sizes = products.page.eval_on_selector_all(
        "[data-testid=product-name], [data-testid=product-price]",
        "els => els.map(e => parseFloat(getComputedStyle(e).fontSize))",
    )

    assert sizes, "No text nodes measured"
    assert min(sizes) >= 12, f"Text smaller than 12px found: {sorted(sizes)[:3]}"


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_layout_survives_rotation(
    playwright: Playwright, browser: Browser, base_url: str, storage_state: str, orientation: str
) -> None:
    """Rotation is a state change most suites never exercise — and a reliable
    source of clipped headers and stuck modals."""
    descriptor = dict(playwright.devices["Pixel 7"])
    viewport = descriptor["viewport"]
    if orientation == "landscape":
        descriptor["viewport"] = {"width": viewport["height"], "height": viewport["width"]}

    context = browser.new_context(**descriptor, base_url=base_url, storage_state=storage_state)
    page = context.new_page()
    try:
        products = App(page).products.open()
        expect(products.testid("product-grid")).to_be_visible()
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 1, f"Horizontal overflow of {overflow}px in {orientation}"
    finally:
        context.close()


@pytest.mark.regression
def test_page_works_on_a_slow_3g_connection(
    playwright: Playwright,
    browser: Browser,
    base_url: str,
    storage_state: str,
    browser_name: str,
) -> None:
    """Network shaping via CDP. Emulating a slow link surfaces missing loading
    states and races that a gigabit office connection hides completely.

    CDP is a Chromium protocol, so this test cannot run on Firefox or WebKit —
    the first cross-browser CI run failed here with "CDP session is only
    available in Chromium". Skipping with an explicit reason is the honest fix:
    the capability genuinely does not exist elsewhere, and a silent pass would
    misrepresent the coverage. For latency on other engines, fall back to
    `page.route` with a delay in the handler, which works everywhere.
    """
    if browser_name != "chromium":
        pytest.skip(f"CDP network shaping is Chromium-only; {browser_name} has no equivalent")

    descriptor = playwright.devices["Pixel 7"]
    context = browser.new_context(**descriptor, base_url=base_url, storage_state=storage_state)
    page = context.new_page()
    try:
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "latency": 400,  # ms RTT
                "downloadThroughput": 400 * 1024 / 8,
                "uploadThroughput": 400 * 1024 / 8,
            },
        )

        products = App(page).products.open()

        expect(products.testid("product-grid")).to_have_attribute(
            "data-loaded", "true", timeout=30_000
        )
        assert products.product_names
    finally:
        context.close()


def test_offline_mode_does_not_show_a_blank_page(
    playwright: Playwright, browser: Browser, base_url: str, storage_state: str
) -> None:
    """Offline is the mobile-specific failure mode. The requirement here is
    modest and non-negotiable: don't render an empty white screen."""
    descriptor = playwright.devices["Pixel 7"]
    context = browser.new_context(**descriptor, base_url=base_url, storage_state=storage_state)
    page = context.new_page()
    try:
        App(page).products.open()
        context.set_offline(True)

        page.get_by_test_id("apply-filters").click()

        # The app currently has no offline handling; assert what it *does* do so
        # the behaviour is pinned and a future improvement is a visible change.
        expect(page.get_by_test_id("status")).not_to_have_text("")
    finally:
        context.set_offline(False)
        context.close()
