"""Screen Object base for Appium (the mobile counterpart of BasePage).

Locator policy, in priority order:
  1. **accessibility id** — maps to `content-desc` (Android) / `accessibilityIdentifier`
     (iOS). One locator, both platforms. Ask developers for these; it is the single
     highest-ROI request a QA engineer can make of a mobile team.
  2. **id / resource-id** — stable but platform-specific.
  3. **-android uiautomator / -ios predicate string** — powerful, native-speed.
  4. **XPath** — last resort. On mobile it is not just ugly, it is *slow*: every
     query serialises the whole view hierarchy over HTTP.

Never use index-based XPath (`(//android.widget.TextView)[3]`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Self

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Selenium's WebElement, not Appium's: `WebDriverWait.until` is typed as returning
# the base class, and Appium's element subclasses it. Annotating with the base
# type keeps mypy happy and loses nothing — every Appium method still resolves.
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from framework.config import Platform, settings
from framework.utils.reporting import attach_png, step

Locator = tuple[str, str]

DEFAULT_TIMEOUT = 15


class BaseScreen:
    #: Locator that proves the screen is displayed. Subclasses must override.
    root: Locator = (AppiumBy.XPATH, "//*")

    def __init__(self, driver: WebDriver, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.driver = driver
        self.timeout = timeout
        self.is_android = settings.mobile.platform is Platform.ANDROID

    # -- waits -------------------------------------------------------------
    def _wait(self, timeout: int | None = None) -> WebDriverWait:
        return WebDriverWait(self.driver, timeout or self.timeout, poll_frequency=0.25)

    def find(self, locator: Locator, timeout: int | None = None) -> WebElement:
        return self._wait(timeout).until(EC.presence_of_element_located(locator))

    def find_visible(self, locator: Locator, timeout: int | None = None) -> WebElement:
        return self._wait(timeout).until(EC.visibility_of_element_located(locator))

    def find_clickable(self, locator: Locator, timeout: int | None = None) -> WebElement:
        return self._wait(timeout).until(EC.element_to_be_clickable(locator))

    def find_all(self, locator: Locator) -> Sequence[WebElement]:
        # Sequence, not list: `list` is invariant, so a list of Appium elements is
        # not a list of Selenium elements even though each item is one.
        self.find(locator)
        return self.driver.find_elements(*locator)

    def is_displayed(self, locator: Locator, timeout: int = 3) -> bool:
        try:
            self.find_visible(locator, timeout)
            return True
        except (TimeoutException, NoSuchElementException):
            return False

    def wait_until_gone(self, locator: Locator, timeout: int | None = None) -> None:
        self._wait(timeout).until(EC.invisibility_of_element_located(locator))

    # -- actions -----------------------------------------------------------
    def tap(self, locator: Locator, description: str = "") -> Self:
        with step(f"Tap {description or locator[1]}"):
            self.find_clickable(locator).click()
        return self

    def type(self, locator: Locator, text: str, *, clear: bool = True) -> Self:
        with step(f"Type '{text}'"):
            element = self.find_visible(locator)
            if clear:
                element.clear()
            element.send_keys(text)
        return self

    def text_of(self, locator: Locator) -> str:
        element = self.find_visible(locator)
        # Android exposes 'text', iOS exposes 'value'/'label'. Normalise here so
        # screens stay platform-agnostic. `get_attribute` can return a dict for
        # some drivers, hence the explicit str() rather than a bare `or`.
        value = element.get_attribute("value")
        return (element.text or (value if isinstance(value, str) else "") or "").strip()

    def hide_keyboard(self) -> Self:
        """Guarded: iOS raises if the keyboard isn't up, Android sometimes lies."""
        try:
            if self.driver.is_keyboard_shown():
                self.driver.hide_keyboard()
        except Exception:  # noqa: BLE001 - keyboard state is genuinely unreliable
            pass
        return self

    # -- gestures (W3C actions via the mobile: scripts) ---------------------
    def swipe(self, direction: str = "up", percent: float = 0.6) -> Self:
        """Scroll the whole screen. Uses the `mobile:` extension commands, which
        are far more reliable than hand-rolled TouchAction sequences (removed in
        Appium 2+)."""
        size = self.driver.get_window_size()
        script = "mobile: swipeGesture" if self.is_android else "mobile: swipe"
        args = (
            {
                "left": int(size["width"] * 0.1),
                "top": int(size["height"] * 0.2),
                "width": int(size["width"] * 0.8),
                "height": int(size["height"] * 0.6),
                "direction": direction,
                "percent": percent,
            }
            if self.is_android
            else {"direction": direction}
        )
        self.driver.execute_script(script, args)
        return self

    def scroll_to_text(self, text: str, max_swipes: int = 8) -> WebElement:
        """Android gets a native scroll-into-view; iOS falls back to swiping."""
        if self.is_android:
            selector = (
                "new UiScrollable(new UiSelector().scrollable(true))"
                f'.scrollIntoView(new UiSelector().textContains("{text}"))'
            )
            return self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, selector)

        locator = (AppiumBy.IOS_PREDICATE, f'label CONTAINS "{text}"')
        for _ in range(max_swipes):
            if self.is_displayed(locator, timeout=1):
                return self.find(locator)
            self.swipe("up")
        raise NoSuchElementException(f"'{text}' not found after {max_swipes} swipes")

    # -- context switching (hybrid apps / webviews) ------------------------
    def switch_to_webview(self, timeout: int = 20) -> str:
        """Hybrid apps render part of the UI in a WebView. Inside it, mobile
        locators stop working and *web* locators (CSS) start working — the single
        biggest gotcha in hybrid testing."""
        deadline = self._wait(timeout)
        deadline.until(lambda d: any("WEBVIEW" in c for c in d.contexts))
        webview = next(c for c in self.driver.contexts if "WEBVIEW" in c)
        self.driver.switch_to.context(webview)
        return webview

    def switch_to_native(self) -> None:
        self.driver.switch_to.context("NATIVE_APP")

    # -- diagnostics -------------------------------------------------------
    def screenshot(self, name: str = "screen") -> bytes:
        data = self.driver.get_screenshot_as_png()
        attach_png(name, data)
        return data

    def wait_until_loaded(self) -> Self:
        self.find_visible(self.root)
        return self


def by_platform(android: Locator, ios: Locator) -> Locator:
    """Pick a locator per platform.

    Use sparingly — every call is a place where the two platforms can drift. If
    more than ~20% of a screen's locators need it, push back and ask for shared
    accessibility ids instead.
    """
    return android if settings.mobile.platform is Platform.ANDROID else ios
