"""ShopAPI — the System Under Test for this course.

Why bundle an app instead of pointing at a public demo site?
  * Deterministic: no rate limits, no third-party outages, tests are reproducible.
  * Offline: the whole course runs on a laptop with no network.
  * Honest: it exposes a real OpenAPI schema (so contract/property-based testing
    has something true to work against) *and* a responsive HTML UI (so the same
    build serves desktop-web, mobile-web and API tests).
  * Teachable: it contains deliberate, documented quirks (see BUGS.md) that the
    exercises ask you to catch.

Run it:  uvicorn sut.app:app --port 8000
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

STATIC_DIR = Path(__file__).parent / "static"

class ErrorResponse(BaseModel):
    detail: str


# Declared on the app so *every* operation documents them. The first run of the
# Schemathesis contract test failed with "Undocumented HTTP status code: 400/401"
# — the tool was right: FastAPI returns those for malformed bodies and missing
# auth, but the spec never said so. Documenting them is the fix. That exchange is
# the whole point of contract testing: it finds the gap between what a service
# does and what it promises.
COMMON_ERRORS: dict = {
    400: {"model": ErrorResponse, "description": "Malformed request body"},
    401: {"model": ErrorResponse, "description": "Missing or invalid credentials"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Conflicting state"},
    # 422 is deliberately absent: FastAPI already documents it with its own
    # HTTPValidationError shape. Overriding it here made the *schema* say
    # `detail: string` while the service returns `detail: [{loc, msg, type}]`,
    # and Schemathesis caught the mismatch on the next run. Second lesson from
    # the same tool: a wrong contract is worse than a missing one.
}

app = FastAPI(
    title="ShopAPI",
    version="1.0.0",
    description="Demo shop used as the System Under Test for the QA automation course.",
    responses=COMMON_ERRORS,
)


# ---------------------------------------------------------------------------
# Schemas — these become the OpenAPI contract that Schemathesis will explore.
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    expires_in: int = Field(description="Token lifetime in seconds")
    username: str


class Product(BaseModel):
    id: int
    name: str
    category: str
    price: float = Field(ge=0)
    in_stock: bool
    rating: float = Field(ge=0, le=5)


class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)

    @field_validator("quantity")
    @classmethod
    def _reject_zero(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be >= 1")
        return v


class CartLine(BaseModel):
    product_id: int
    name: str
    unit_price: float
    quantity: int
    line_total: float


class Cart(BaseModel):
    items: list[CartLine]
    total: float
    currency: str = "USD"


class Order(BaseModel):
    id: str
    status: str
    total: float
    items: list[CartLine]
    created_at: float


# ---------------------------------------------------------------------------
# In-memory state. Reset between test sessions via POST /api/testing/reset.
# A reset hook is one of the highest-leverage things a team can ask backend for.
# ---------------------------------------------------------------------------
USERS = {"alice": "wonderland", "bob": "builder"}

PRODUCTS: list[Product] = [
    Product(id=1, name="Aurora Headphones", category="audio", price=199.99, in_stock=True, rating=4.6),
    Product(id=2, name="Bassline Speaker", category="audio", price=89.50, in_stock=True, rating=4.1),
    Product(id=3, name="Comet Keyboard", category="input", price=129.00, in_stock=True, rating=4.8),
    Product(id=4, name="Drift Mouse", category="input", price=49.00, in_stock=False, rating=3.9),
    Product(id=5, name="Ember Monitor", category="display", price=349.00, in_stock=True, rating=4.4),
    Product(id=6, name="Flux Webcam", category="video", price=79.99, in_stock=True, rating=3.5),
]

_SESSIONS: dict[str, str] = {}       # token -> username
_CARTS: dict[str, list[CartItem]] = {}  # username -> items
_ORDERS: dict[str, Order] = {}


def _reset_state() -> None:
    _SESSIONS.clear()
    _CARTS.clear()
    _ORDERS.clear()


def current_user(authorization: Annotated[str | None, Header()] = None) -> str:
    """Bearer-token auth. Deliberately strict: a missing header is 401, not 403."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    username = _SESSIONS.get(token)
    if username is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return username


CurrentUser = Annotated[str, Depends(current_user)]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.post("/api/auth/login", response_model=LoginResponse, responses={401: {"model": ErrorResponse}})
def login(payload: LoginRequest) -> LoginResponse:
    if USERS.get(payload.username) != payload.password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = secrets.token_hex(16)
    _SESSIONS[token] = payload.username
    return LoginResponse(token=token, expires_in=3600, username=payload.username)


@app.post(
    "/api/auth/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
def register(payload: LoginRequest) -> LoginResponse:
    """Create an account and return a session.

    Added specifically so the test suite can give **every parallel worker its own
    user**. Before this existed, four xdist workers shared `alice` and stomped on
    each other's carts. Self-service test-data creation is the single most
    valuable thing a backend can offer a test suite; ask for it early.
    """
    if payload.username in USERS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"User {payload.username} already exists")
    USERS[payload.username] = payload.password
    token = secrets.token_hex(16)
    _SESSIONS[token] = payload.username
    return LoginResponse(token=token, expires_in=3600, username=payload.username)


@app.get("/api/products", response_model=list[Product])
def list_products(
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Case-insensitive name search"),
    in_stock: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Product]:
    items = PRODUCTS
    if category:
        items = [p for p in items if p.category == category]
    if q:
        items = [p for p in items if q.lower() in p.name.lower()]
    if in_stock is not None:
        items = [p for p in items if p.in_stock is in_stock]
    return items[:limit]


@app.get("/api/products/{product_id}", response_model=Product, responses={404: {"model": ErrorResponse}})
def get_product(product_id: int) -> Product:
    for p in PRODUCTS:
        if p.id == product_id:
            return p
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")


def _build_cart(username: str) -> Cart:
    lines: list[CartLine] = []
    by_id = {p.id: p for p in PRODUCTS}
    for item in _CARTS.get(username, []):
        product = by_id[item.product_id]
        lines.append(
            CartLine(
                product_id=product.id,
                name=product.name,
                unit_price=product.price,
                quantity=item.quantity,
                line_total=round(product.price * item.quantity, 2),
            )
        )
    return Cart(items=lines, total=round(sum(line.line_total for line in lines), 2))


@app.get("/api/cart", response_model=Cart)
def get_cart(user: CurrentUser) -> Cart:
    return _build_cart(user)


@app.post("/api/cart/items", response_model=Cart, status_code=status.HTTP_201_CREATED)
def add_to_cart(item: CartItem, user: CurrentUser) -> Cart:
    product = next((p for p in PRODUCTS if p.id == item.product_id), None)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {item.product_id} not found")
    if not product.in_stock:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Product {item.product_id} is out of stock")

    cart = _CARTS.setdefault(user, [])
    for existing in cart:
        if existing.product_id == item.product_id:
            existing.quantity = min(99, existing.quantity + item.quantity)
            break
    else:
        cart.append(item)
    return _build_cart(user)


@app.delete("/api/cart/items/{product_id}", response_model=Cart)
def remove_from_cart(product_id: int, user: CurrentUser) -> Cart:
    cart = _CARTS.get(user, [])
    _CARTS[user] = [i for i in cart if i.product_id != product_id]
    return _build_cart(user)


@app.post("/api/orders", response_model=Order, status_code=status.HTTP_201_CREATED)
def create_order(user: CurrentUser) -> Order:
    cart = _build_cart(user)
    if not cart.items:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cannot place an order with an empty cart")
    order = Order(
        id=f"ord_{secrets.token_hex(6)}",
        status="confirmed",
        total=cart.total,
        items=cart.items,
        created_at=time.time(),
    )
    _ORDERS[order.id] = order
    _CARTS[user] = []
    return order


@app.get("/api/orders/{order_id}", response_model=Order, responses={404: {"model": ErrorResponse}})
def get_order(order_id: str, user: CurrentUser) -> Order:
    order = _ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")
    return order


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/testing/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset() -> None:
    """Test-only hook. Real systems should expose an equivalent, gated by env."""
    _reset_state()


# ---------------------------------------------------------------------------
# UI — one responsive page set, driven by both desktop-web and mobile-web tests.
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _page(name: str) -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / name).read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
def ui_home() -> HTMLResponse:
    return _page("index.html")


@app.get("/login", response_class=HTMLResponse)
def ui_login() -> HTMLResponse:
    return _page("login.html")


@app.get("/cart", response_class=HTMLResponse)
def ui_cart() -> HTMLResponse:
    return _page("cart.html")
