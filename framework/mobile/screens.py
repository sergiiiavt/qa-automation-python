"""Screen Objects for the bundled native app, plus a mobile-web screen.

The native screens target Sauce Labs' "My Demo App" — see
[apps/README.md](../../apps/README.md) for what it is and why it's bundled.

**Every locator below was verified against that exact build.** That is a
deliberate constraint, not an oversight: `CatalogScreen`, `MenuScreen` and
`LoginScreen` cover the app's login flow end to end and nothing here is
guessed. The product-detail, add-to-cart and checkout screens are *not*
modelled — nobody had checked their resource ids before this course was
written, and shipping invented locators that merely *look* plausible would
teach the opposite of what this framework is for. Building those screens
yourself, with Appium Inspector, is Exercise 22b in
[docs/10-exercises.md](../../docs/10-exercises.md).

The *structure* — one class per screen, intent-named methods, locators as
class attributes — is what transfers to your own app. Swap `APP_PACKAGE` and
every resource id for yours; nothing else here is app-specific.
"""

from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy

from framework.mobile.base_screen import BaseScreen, Locator
from framework.utils.reporting import step

#: com.saucelabs.mydemoapp.android — see apps/README.md.
APP_PACKAGE = "com.saucelabs.mydemoapp.android"

# The app's three fixed demo accounts (documented in Sauce Labs' own repo).
VALID_USERNAME = "bod@example.com"
VALID_PASSWORD = "10203040"
LOCKED_OUT_USERNAME = "alice@example.com"


class CatalogScreen(BaseScreen):
    """The product catalog — the app's landing screen after launch."""

    root = (AppiumBy.ID, f"{APP_PACKAGE}:id/menuIV")
    MENU_BUTTON: Locator = (AppiumBy.ID, f"{APP_PACKAGE}:id/menuIV")
    PRODUCT_LIST: Locator = (AppiumBy.ID, f"{APP_PACKAGE}:id/productRV")

    def open_menu(self) -> MenuScreen:
        with step("Mobile: open the hamburger menu"):
            self.tap(self.MENU_BUTTON, "Menu")
        return MenuScreen(self.driver).wait_until_loaded()


class MenuScreen(BaseScreen):
    """The side navigation drawer, reached from the catalog's hamburger icon."""

    root = (AppiumBy.ID, f"{APP_PACKAGE}:id/menuRV")
    LOGIN_ITEM_DESC = "Login Menu Item"
    LOGOUT_ITEM_DESC = "Logout Menu Item"

    def open_login(self) -> LoginScreen:
        with step("Mobile: open Login from the menu"):
            self._scroll_to_and_tap(self.LOGIN_ITEM_DESC)
        return LoginScreen(self.driver).wait_until_loaded()

    def open_logout(self) -> CatalogScreen:
        with step("Mobile: log out from the menu"):
            self._scroll_to_and_tap(self.LOGOUT_ITEM_DESC)
        return CatalogScreen(self.driver).wait_until_loaded()

    def _scroll_to_and_tap(self, content_description: str) -> None:
        # The login/logout entry sits at the bottom of a RecyclerView and may
        # not be rendered yet. UiScrollable drives Android's native scrolling
        # until the item is in view; a Python swipe loop would be slower and
        # less reliable for exactly this reason.
        locator: Locator = (
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiScrollable(new UiSelector().resourceId("{self.root[1]}")).scrollIntoView('
            f'new UiSelector().description("{content_description}"))',
        )
        self.tap(locator, content_description)


class LoginScreen(BaseScreen):
    """Reached via the catalog's hamburger menu, not directly from launch."""

    root = (AppiumBy.ID, f"{APP_PACKAGE}:id/nameET")
    USERNAME_FIELD: Locator = (AppiumBy.ID, f"{APP_PACKAGE}:id/nameET")
    PASSWORD_FIELD: Locator = (AppiumBy.ID, f"{APP_PACKAGE}:id/passwordET")
    LOGIN_BUTTON: Locator = (AppiumBy.ID, f"{APP_PACKAGE}:id/loginBtn")
    USERNAME_ERROR: Locator = (AppiumBy.ID, f"{APP_PACKAGE}:id/nameErrorTV")
    PASSWORD_ERROR: Locator = (AppiumBy.ID, f"{APP_PACKAGE}:id/passwordErrorTV")

    def login(self, username: str, password: str) -> CatalogScreen:
        with step(f"Mobile: log in as {username or '<blank>'}"):
            if username:
                self.type(self.USERNAME_FIELD, username)
            if password:
                self.type(self.PASSWORD_FIELD, password)
            self.hide_keyboard()
            self.tap(self.LOGIN_BUTTON, "Log in")
        return CatalogScreen(self.driver).wait_until_loaded()

    def login_expecting_failure(self, username: str, password: str) -> LoginScreen:
        if username:
            self.type(self.USERNAME_FIELD, username)
        if password:
            self.type(self.PASSWORD_FIELD, password)
        self.hide_keyboard()
        self.tap(self.LOGIN_BUTTON, "Log in")
        return self

    @property
    def username_error(self) -> str:
        return self.text_of(self.USERNAME_ERROR)

    @property
    def password_error(self) -> str:
        return self.text_of(self.PASSWORD_ERROR)


# ---------------------------------------------------------------------------
# Mobile web: the course's own bundled site, driven through a real mobile
# browser via Appium. Unrelated to the app above — see docs/05-mobile.md for
# why "real-device mobile web" and "native app" are deliberately kept as two
# separate targets rather than forced into one.
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
