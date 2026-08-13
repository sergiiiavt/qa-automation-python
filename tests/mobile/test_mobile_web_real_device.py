"""Mobile web on a REAL device/browser, via Appium.

The counterpart to `tests/web/test_mobile_web.py` (emulated). Run these on a
nightly/release cadence — they are 20-50x slower than emulation and need a
device or a device cloud.

What only a real device can tell you:
  * genuine WebKit behaviour on iOS (every iOS browser is Safari underneath);
  * true viewport arithmetic with the browser chrome, notch and home indicator;
  * real scroll momentum, pinch-zoom, and the soft-keyboard shrinking the viewport;
  * actual font rendering and system font fallback;
  * device-level performance on mid-range hardware, which is what users have.
"""

from __future__ import annotations

import pytest
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from framework.config import settings
from framework.mobile.screens import MobileWebShop

pytestmark = [pytest.mark.mobile_native, pytest.mark.mobile_web, pytest.mark.slow]


@pytest.fixture
def shop(mobile_web_driver, base_url: str) -> MobileWebShop:
    return MobileWebShop(mobile_web_driver).open(base_url)


def test_site_loads_and_renders_products(shop: MobileWebShop) -> None:
    assert shop.product_names, "No products rendered on the device browser"


def test_hamburger_menu_works_with_a_real_tap(shop: MobileWebShop) -> None:
    """A real tap goes through the OS touch stack. Elements that respond to a
    synthetic click but not a tap — overlays, 300ms-delay handlers, elements
    covered by a sticky header — only fail here."""
    shop.open_menu()

    nav = shop.find_visible(MobileWebShop.NAV)

    assert nav.is_displayed()


def test_no_horizontal_overflow_on_the_device_viewport(shop: MobileWebShop) -> None:
    overflow = shop.driver.execute_script(
        "return document.documentElement.scrollWidth - document.documentElement.clientWidth;"
    )

    assert overflow <= 1, f"Real device shows {overflow}px of horizontal overflow"


def test_soft_keyboard_does_not_hide_the_search_field(shop: MobileWebShop) -> None:
    """The soft keyboard resizes the visual viewport on real devices — a whole
    class of "the input scrolls off screen" bugs that emulation cannot reproduce."""
    field = shop.find_visible(MobileWebShop.SEARCH)
    field.click()
    field.send_keys("aurora")

    viewport_height = shop.driver.execute_script("return window.innerHeight;")
    field_bottom = shop.driver.execute_script(
        "const r = arguments[0].getBoundingClientRect(); return r.bottom;", field
    )

    assert field_bottom <= viewport_height, (
        "The search field is hidden behind the soft keyboard while typing"
    )


def test_search_works_end_to_end(shop: MobileWebShop) -> None:
    shop.search("aurora")

    WebDriverWait(shop.driver, 15).until(
        EC.presence_of_element_located(MobileWebShop.CARDS)
    )

    assert all("aurora" in name.lower() for name in shop.product_names)


@pytest.mark.skipif(
    not settings.mobile.cloud_user,
    reason="Requires a device cloud; local emulators cannot vary the device model",
)
def test_layout_on_the_smallest_supported_device(shop: MobileWebShop) -> None:
    """Run the same assertions across the real device matrix your analytics say
    users have. Pick devices from data, not from what's on the shelf."""
    width = shop.driver.execute_script("return window.innerWidth;")

    assert width >= 320, f"Unsupported viewport width {width}"
    assert shop.product_names
