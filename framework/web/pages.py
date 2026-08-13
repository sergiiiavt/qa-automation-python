"""Concrete Page Objects and one Component.

Note `ProductCard`: a *component*, not a page. As soon as a repeated UI block has
its own behaviour, give it a class scoped to its root locator. Component objects
are what keep Page Objects from growing into 600-line god classes with names like
`click_add_to_cart_button_in_third_card`.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

from framework.utils.reporting import step
from framework.web.base_page import BasePage


class ProductCard:
    """Scoped to one card's root element; every lookup is relative to it."""

    def __init__(self, root: Locator) -> None:
        self.root = root

    @property
    def name(self) -> str:
        return self.root.get_by_test_id("product-name").inner_text().strip()

    @property
    def category(self) -> str:
        return self.root.get_by_test_id("product-category").inner_text().strip()

    @property
    def price(self) -> float:
        return float(self.root.get_by_test_id("product-price").inner_text().strip().lstrip("$"))

    @property
    def product_id(self) -> int:
        return int(self.root.get_attribute("data-product-id") or 0)

    @property
    def in_stock(self) -> bool:
        return "In stock" in self.root.get_by_test_id("stock-badge").inner_text()

    def add_to_cart(self) -> None:
        with step(f"Add '{self.name}' to cart"):
            self.root.get_by_test_id("add-to-cart").click()


class LoginPage(BasePage):
    path = "/login"
    ready_locator = "[data-testid=login-form]"

    @property
    def username(self) -> Locator:
        return self.testid("username")

    @property
    def password(self) -> Locator:
        return self.testid("password")

    @property
    def submit(self) -> Locator:
        return self.testid("submit")

    @property
    def error(self) -> Locator:
        return self.testid("error")

    def login(self, username: str, password: str) -> ProductsPage:
        """Happy path: fills, submits, and returns the *next* page object.

        Returning the destination page is what lets a test chain steps without
        knowing the navigation graph:
            products = LoginPage(page).open().login(u, p)
        """
        with step(f"Log in as {username}"):
            self.username.fill(username)
            self.password.fill(password)
            self.submit.click()
        products = ProductsPage(self.page)
        products.wait_until_ready()
        return products

    def login_expecting_failure(self, username: str, password: str) -> LoginPage:
        """Negative path stays on this page. Separate method, separate return
        type — never `-> LoginPage | ProductsPage`."""
        self.username.fill(username)
        self.password.fill(password)
        self.submit.click()
        expect(self.error).not_to_be_empty()
        return self


class ProductsPage(BasePage):
    path = "/"
    ready_locator = "[data-testid=product-grid][data-loaded=true]"

    @property
    def search_input(self) -> Locator:
        return self.testid("search-input")

    @property
    def category_filter(self) -> Locator:
        return self.testid("category-filter")

    @property
    def status(self) -> Locator:
        return self.testid("status")

    @property
    def cards(self) -> list[ProductCard]:
        cards = self.testid("product-card")
        expect(cards.first).to_be_visible()
        return [ProductCard(cards.nth(i)) for i in range(cards.count())]

    def card_for(self, name: str) -> ProductCard:
        root = self.testid("product-card").filter(has_text=name)
        expect(root).to_have_count(1)
        return ProductCard(root)

    def search(self, term: str) -> ProductsPage:
        with step(f"Search for '{term}'"):
            self.search_input.fill(term)
            self.testid("apply-filters").click()
            # The app stamps data-loaded when rendering finishes — assert on that,
            # never on a timeout.
            expect(self.testid("product-grid")).to_have_attribute("data-loaded", "true")
        return self

    def filter_by_category(self, category: str) -> ProductsPage:
        self.category_filter.select_option(category)
        self.testid("apply-filters").click()
        expect(self.testid("product-grid")).to_have_attribute("data-loaded", "true")
        return self

    @property
    def product_names(self) -> list[str]:
        return [c.name for c in self.cards]


class CartPage(BasePage):
    path = "/cart"
    ready_locator = "[data-testid=cart-table]"

    @property
    def rows(self) -> Locator:
        return self.testid("cart-row")

    @property
    def total(self) -> float:
        return float(self.testid("cart-total").inner_text().strip().lstrip("$"))

    @property
    def status(self) -> Locator:
        return self.testid("status")

    def row_for(self, name: str) -> Locator:
        return self.rows.filter(has_text=name)

    def quantity_of(self, name: str) -> int:
        return int(self.row_for(name).get_by_test_id("row-qty").inner_text())

    def remove(self, name: str) -> CartPage:
        with step(f"Remove '{name}' from cart"):
            row = self.row_for(name)
            row.get_by_test_id("remove").click()
            expect(row).to_have_count(0)
        return self

    def checkout(self) -> CartPage:
        with step("Place order"):
            self.testid("checkout").click()
            expect(self.status).to_contain_text("confirmed")
        return self

    @property
    def is_empty(self) -> bool:
        return self.testid("empty-cart").is_visible()


class App:
    """Entry point that hands out pages. Injected as a single `app` fixture."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.login = LoginPage(page)
        self.products = ProductsPage(page)
        self.cart = CartPage(page)
