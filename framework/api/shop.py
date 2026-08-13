"""Service objects — the API-layer equivalent of Page Objects.

Each class owns one resource: its paths, its payload shapes, its response models.
Tests read like the business flow, not like HTTP.

Two return styles, on purpose:
  * `add_item(...) -> Cart`        happy path: parsed, typed, ready to assert on.
  * `add_item_raw(...) -> Response` negative path: status codes and error bodies.

Mixing them into one method that "sometimes parses" is the most common way these
layers rot. Keep them separate.
"""

from __future__ import annotations

import httpx

from framework.api.models import Cart, LoginResponse, Order, Product
from framework.http.client import ApiClient
from framework.utils.reporting import step


class BaseApi:
    def __init__(self, client: ApiClient) -> None:
        self.client = client


class AuthApi(BaseApi):
    PATH = "/api/auth/login"

    def login(self, username: str, password: str) -> LoginResponse:
        with step(f"API: log in as {username}"):
            response = self.client.post(
                self.PATH, json={"username": username, "password": password}, expect=200
            )
            return LoginResponse.model_validate(response.json())

    def login_raw(self, username: str, password: str) -> httpx.Response:
        return self.client.post(self.PATH, json={"username": username, "password": password})

    def authenticate(self, username: str, password: str) -> str:
        """Log in and attach the token to the underlying client."""
        token = self.login(username, password).token
        self.client.with_token(token)
        return token


class ProductsApi(BaseApi):
    PATH = "/api/products"

    def list(
        self,
        *,
        category: str | None = None,
        q: str | None = None,
        in_stock: bool | None = None,
        limit: int | None = None,
    ) -> list[Product]:
        params = {k: v for k, v in
                  {"category": category, "q": q, "in_stock": in_stock, "limit": limit}.items()
                  if v is not None}
        with step(f"API: list products {params or '(no filter)'}"):
            response = self.client.get(self.PATH, params=params, expect=200)
            return [Product.model_validate(item) for item in response.json()]

    def get(self, product_id: int) -> Product:
        with step(f"API: get product {product_id}"):
            response = self.client.get(f"{self.PATH}/{product_id}", expect=200)
            return Product.model_validate(response.json())

    def get_raw(self, product_id: int | str) -> httpx.Response:
        return self.client.get(f"{self.PATH}/{product_id}")

    def first_in_stock(self) -> Product:
        products = self.list(in_stock=True)
        assert products, "SUT has no in-stock products — fixture data is broken"
        return products[0]

    def first_out_of_stock(self) -> Product:
        products = self.list(in_stock=False)
        assert products, "SUT has no out-of-stock products — fixture data is broken"
        return products[0]


class CartApi(BaseApi):
    PATH = "/api/cart"

    def get(self) -> Cart:
        with step("API: read cart"):
            return Cart.model_validate(self.client.get(self.PATH, expect=200).json())

    def add_item(self, product_id: int, quantity: int = 1) -> Cart:
        with step(f"API: add product {product_id} x{quantity} to cart"):
            response = self.client.post(
                f"{self.PATH}/items",
                json={"product_id": product_id, "quantity": quantity},
                expect=201,
            )
            return Cart.model_validate(response.json())

    def add_item_raw(self, product_id: object, quantity: object = 1) -> httpx.Response:
        return self.client.post(
            f"{self.PATH}/items", json={"product_id": product_id, "quantity": quantity}
        )

    def remove_item(self, product_id: int) -> Cart:
        with step(f"API: remove product {product_id} from cart"):
            response = self.client.delete(f"{self.PATH}/items/{product_id}", expect=200)
            return Cart.model_validate(response.json())

    def clear(self) -> None:
        for line in self.get().items:
            self.remove_item(line.product_id)


class OrdersApi(BaseApi):
    PATH = "/api/orders"

    def create(self) -> Order:
        with step("API: place order"):
            return Order.model_validate(self.client.post(self.PATH, expect=201).json())

    def create_raw(self) -> httpx.Response:
        return self.client.post(self.PATH)

    def get(self, order_id: str) -> Order:
        return Order.model_validate(self.client.get(f"{self.PATH}/{order_id}", expect=200).json())


class ShopApi:
    """Facade: one object a test can hold that reaches the whole API.

    `shop.cart.add_item(...)` beats wiring four fixtures into every signature.
    """

    def __init__(self, client: ApiClient) -> None:
        self.client = client
        self.auth = AuthApi(client)
        self.products = ProductsApi(client)
        self.cart = CartApi(client)
        self.orders = OrdersApi(client)

    def login_as(self, username: str, password: str) -> ShopApi:
        self.auth.authenticate(username, password)
        return self

    def reset(self) -> None:
        """Wipe SUT state. Only safe against non-production environments."""
        self.client.post("/api/testing/reset", expect=204)
