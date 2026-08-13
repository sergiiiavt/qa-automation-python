"""Page Object base for Playwright.

Three rules this base enforces:

1. **No explicit sleeps, ever.** Playwright locators auto-wait. If you find
   yourself reaching for `time.sleep`, the missing thing is a *state* to wait for
   (`expect(...).to_be_visible()`), not a duration.

2. **Locators are lazy, elements are not.** `page.get_by_test_id("x")` is a
   query description, resolved at action time. Storing a resolved element handle
   in `__init__` is what makes Page Objects go stale on re-render. Every locator
   here is a `@property` returning a fresh `Locator`.

3. **Page Objects expose intent, not clicks.** `login(user, pw)` — not
   `type_username`, `type_password`, `click_submit`. The test should read like
   the acceptance criterion.
"""

from __future__ import annotations

from typing import Self
from urllib.parse import urljoin

from playwright.sync_api import Locator, Page, expect

from framework.config import settings
from framework.utils.reporting import attach_png, step


class BasePage:
    #: Path relative to web.base_url. Subclasses override.
    path: str = "/"
    #: A locator that proves the page finished rendering. Subclasses override.
    ready_locator: str = "body"

    def __init__(self, page: Page) -> None:
        self.page = page
        self.base_url = settings.web.base_url.rstrip("/")

    # -- navigation --------------------------------------------------------
    @property
    def url(self) -> str:
        return urljoin(self.base_url + "/", self.path.lstrip("/"))

    def open(self, **query: str) -> Self:
        target = self.url
        if query:
            from urllib.parse import urlencode

            target = f"{target}?{urlencode(query)}"
        with step(f"Open {target}"):
            self.page.goto(target, wait_until="domcontentloaded")
            return self.wait_until_ready()

    def wait_until_ready(self) -> Self:
        expect(self.page.locator(self.ready_locator).first).to_be_visible()
        return self

    def reload(self) -> Self:
        self.page.reload(wait_until="domcontentloaded")
        return self.wait_until_ready()

    # -- locator helpers ---------------------------------------------------
    def testid(self, value: str) -> Locator:
        """Prefer data-testid. It is the only selector the product team can't
        break by redesigning, and the only one a designer can't break by renaming
        a CSS class. Configure the attribute once in conftest via
        `playwright.selectors.set_test_id_attribute`."""
        return self.page.get_by_test_id(value)

    def role(self, role: str, name: str | None = None, **kw: object) -> Locator:
        """Role-based lookup — the closest a test gets to 'what the user sees'.
        Use it for anything a screen reader would announce; it doubles as a
        cheap accessibility signal (if `get_by_role` can't find it, neither can
        assistive tech)."""
        return self.page.get_by_role(role, name=name, **kw)  # type: ignore[arg-type]

    # -- state -------------------------------------------------------------
    @property
    def is_mobile_layout(self) -> bool:
        """True when the responsive breakpoint has collapsed the nav.

        Same Page Object, both layouts. Duplicating a whole `MobileHomePage`
        class for a responsive site is the classic wrong turn — branch on the
        one thing that actually differs.
        """
        viewport = self.page.viewport_size
        return bool(viewport and viewport["width"] <= 640)

    def open_nav(self) -> Self:
        """Desktop: nav is always visible. Mobile: it lives behind a hamburger."""
        if self.is_mobile_layout:
            toggle = self.testid("menu-toggle")
            if toggle.get_attribute("aria-expanded") != "true":
                toggle.click()
            expect(self.testid("main-nav")).to_be_visible()
        return self

    def screenshot(self, name: str = "screenshot", *, full_page: bool = True) -> bytes:
        data = self.page.screenshot(full_page=full_page)
        attach_png(name, data)
        return data

    # -- shared header -----------------------------------------------------
    @property
    def cart_count(self) -> int:
        return int(self.testid("cart-count").inner_text().strip() or 0)

    def go_to_cart(self) -> None:
        self.open_nav()
        self.testid("cart-link").click()
