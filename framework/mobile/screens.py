"""Screen Objects for the demo native app, plus a mobile-web screen.

The native screens target a generic sample shop app; swap the locators for your
own app's. The *structure* — one class per screen, intent-named methods,
platform-split locators isolated in `by_platform` — is what transfers.
"""

from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC

from framework.mobile.base_screen import BaseScreen, Locator, by_platform
from framework.utils.reporting import step


class LoginScreen(BaseScreen):
    root = by_platform(
        (AppiumBy.ACCESSIBILITY_ID, "login-screen"),
        (AppiumBy.ACCESSIBILITY_ID, "login-screen"),
    )
    USERNAME: Locator = (AppiumBy.ACCESSIBILITY_ID, "username-input")
    PASSWORD: Locator = (AppiumBy.ACCESSIBILITY_ID, "password-input")
    SUBMIT: Locator = (AppiumBy.ACCESSIBILITY_ID, "login-button")
    ERROR: Locator = by_platform(
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceIdMatches(".*error_text")'),
        (AppiumBy.IOS_PREDICATE, 'name == "error-text"'),
    )

    def login(self, username: str, password: str) -> ProductsScreen:
        with step(f"Mobile: log in as {username}"):
            self.type(self.USERNAME, username)
            self.type(self.PASSWORD, password)
            self.hide_keyboard()
            self.tap(self.SUBMIT, "Log in")
        return ProductsScreen(self.driver).wait_until_loaded()

    def login_expecting_failure(self, username: str, password: str) -> LoginScreen:
        self.type(self.USERNAME, username)
        self.type(self.PASSWORD, password)
        self.hide_keyboard()
        self.tap(self.SUBMIT, "Log in")
        self.find_visible(self.ERROR)
        return self

    @property
    def error_text(self) -> str:
        return self.text_of(self.ERROR)


class ProductsScreen(BaseScreen):
    root = (AppiumBy.ACCESSIBILITY_ID, "products-screen")
    SEARCH: Locator = (AppiumBy.ACCESSIBILITY_ID, "search-input")
    CART_BUTTON: Locator = (AppiumBy.ACCESSIBILITY_ID, "cart-button")
    CART_BADGE: Locator = (AppiumBy.ACCESSIBILITY_ID, "cart-badge")
    PRODUCT_TITLES: Locator = by_platform(
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceIdMatches(".*product_title")'),
        (AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeStaticText[`name == "product-title"`]'),
    )

    def search(self, term: str) -> ProductsScreen:
        self.type(self.SEARCH, term)
        self.driver.execute_script(
            "mobile: performEditorAction", {"action": "search"}
        ) if self.is_android else self.hide_keyboard()
        return self

    @property
    def product_names(self) -> list[str]:
        return [e.text for e in self.find_all(self.PRODUCT_TITLES)]

    def add_to_cart(self, product_name: str) -> ProductsScreen:
        with step(f"Mobile: add '{product_name}' to cart"):
            self.scroll_to_text(product_name)
            # The Add button sits inside the product row; walk up from the title.
            row_button = by_platform(
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().descriptionContains("add-{product_name}")',
                ),
                (AppiumBy.IOS_PREDICATE, f'name == "add-{product_name}"'),
            )
            self.tap(row_button, f"Add {product_name}")
        return self

    @property
    def cart_count(self) -> int:
        if not self.is_displayed(self.CART_BADGE, timeout=2):
            return 0
        return int(self.text_of(self.CART_BADGE) or 0)

    def open_cart(self) -> CartScreen:
        self.tap(self.CART_BUTTON, "Cart")
        return CartScreen(self.driver).wait_until_loaded()


class CartScreen(BaseScreen):
    root = (AppiumBy.ACCESSIBILITY_ID, "cart-screen")
    TOTAL: Locator = (AppiumBy.ACCESSIBILITY_ID, "cart-total")
    CHECKOUT: Locator = (AppiumBy.ACCESSIBILITY_ID, "checkout-button")
    EMPTY_LABEL: Locator = (AppiumBy.ACCESSIBILITY_ID, "empty-cart")
    CONFIRMATION: Locator = (AppiumBy.ACCESSIBILITY_ID, "order-confirmation")

    @property
    def total(self) -> float:
        return float(self.text_of(self.TOTAL).lstrip("$"))

    @property
    def is_empty(self) -> bool:
        return self.is_displayed(self.EMPTY_LABEL, timeout=3)

    def checkout(self) -> CartScreen:
        with step("Mobile: place order"):
            self.tap(self.CHECKOUT, "Place order")
            self._wait().until(EC.visibility_of_element_located(self.CONFIRMATION))
        return self

    @property
    def confirmation_text(self) -> str:
        return self.text_of(self.CONFIRMATION)


# ---------------------------------------------------------------------------
# Mobile web: same site, driven through a real mobile browser via Appium.
# Locators are CSS, because inside a browser session Appium *is* Selenium.
# ---------------------------------------------------------------------------
class MobileWebShop(BaseScreen):
    """Minimal mobile-web screen object.

    Note what changes vs. native: `AppiumBy.CSS_SELECTOR` works, `swipe` is
    replaced by JS scrolling, and the DOM — not the view hierarchy — is the
    source of truth. Everything else (waits, intent methods) is identical.
    """

    root = (AppiumBy.CSS_SELECTOR, "[data-testid=product-grid]")
    MENU_TOGGLE: Locator = (AppiumBy.CSS_SELECTOR, "[data-testid=menu-toggle]")
    NAV: Locator = (AppiumBy.CSS_SELECTOR, "[data-testid=main-nav]")
    CART_LINK: Locator = (AppiumBy.CSS_SELECTOR, "[data-testid=cart-link]")
    CARDS: Locator = (AppiumBy.CSS_SELECTOR, "[data-testid=product-card]")
    SEARCH: Locator = (AppiumBy.CSS_SELECTOR, "[data-testid=search-input]")
    APPLY: Locator = (AppiumBy.CSS_SELECTOR, "[data-testid=apply-filters]")

    def open(self, url: str) -> MobileWebShop:
        self.driver.get(url)
        return self.wait_until_loaded()

    def open_menu(self) -> MobileWebShop:
        if self.is_displayed(self.MENU_TOGGLE, timeout=2):
            self.tap(self.MENU_TOGGLE, "hamburger menu")
        return self

    def search(self, term: str) -> MobileWebShop:
        self.type(self.SEARCH, term)
        self.tap(self.APPLY, "Apply")
        return self

    @property
    def product_names(self) -> list[str]:
        return [
            e.text for e in self.find_all((AppiumBy.CSS_SELECTOR, "[data-testid=product-name]"))
        ]
