"""Response models.

These are *the test suite's own* view of the contract — intentionally a separate
declaration from the server's. If someone silently renames `total` to `sum`,
`Cart.model_validate(...)` fails loudly. Sharing the server's models would make
that class of bug invisible, which is why production models are not imported here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Base: unknown fields are an error.

    `extra="forbid"` is the aggressive choice, and it is the right default for a
    test suite: a new undocumented field in a response is exactly the drift you
    want a build to tell you about. Relax it per-model if your API is additive
    by design.

    `frozen=True` blocks reassigning a field on the model itself (`resp.total =
    5` raises) and makes the model hashable. It does *not* deep-freeze: a field
    typed `list[Item]` still holds a plain, mutable list, so `resp.items.append(...)`
    succeeds silently. Reach for a tuple/frozen-collection field type if a
    nested value genuinely needs to be immutable too.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class LoginResponse(Strict):
    token: str = Field(min_length=8)
    expires_in: int = Field(gt=0)
    username: str


class Product(Strict):
    id: int
    name: str
    category: str
    price: float = Field(ge=0)
    in_stock: bool
    rating: float = Field(ge=0, le=5)


class CartLine(Strict):
    product_id: int
    name: str
    unit_price: float
    quantity: int = Field(ge=1)
    line_total: float


class Cart(Strict):
    items: list[CartLine]
    total: float
    currency: str

    def line_for(self, product_id: int) -> CartLine | None:
        return next((i for i in self.items if i.product_id == product_id), None)

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.items)


class Order(Strict):
    id: str
    status: str
    total: float
    items: list[CartLine]
    created_at: float


class ErrorResponse(Strict):
    detail: str
