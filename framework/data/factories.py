"""Test data: builders, factories, and the rules that keep data from causing flake.

Three principles:

1. **Every test creates the data it needs.** Shared golden records are the #1
   cause of "passes alone, fails in parallel".
2. **Unique by construction.** Any field with a uniqueness constraint gets a
   worker-aware unique suffix, so `-n auto` doesn't collide.
3. **Specify only what the test is about.** `UserBuilder().with_email(...)` —
   everything else is filled in. When a test names a value, that value should be
   load-bearing for the assertion; otherwise it is noise the reader must check.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field, replace
from typing import Self

from faker import Faker
from polyfactory.factories.pydantic_factory import ModelFactory

from framework.api.models import Product

fake = Faker()
Faker.seed(int(os.getenv("QA_FAKER_SEED", "0")) or None)


def unique_suffix() -> str:
    """Collision-resistant across xdist workers and across reruns of the same
    worker -- not collision-proof. 8 hex chars is 32 bits of entropy per worker
    (~1e-6 collision odds even at thousands of calls), fine for throwaway test
    data. If a test's correctness depends on true uniqueness rather than "so
    unlikely it won't happen in this suite's lifetime," use the full UUID."""
    worker = os.getenv("PYTEST_XDIST_WORKER", "gw0")
    return f"{worker}-{uuid.uuid4().hex[:8]}"


def unique_email(prefix: str = "qa") -> str:
    return f"{prefix}+{unique_suffix()}@example.test"


def unique_username(prefix: str = "user") -> str:
    return f"{prefix}_{unique_suffix()}"


# ---------------------------------------------------------------------------
# Builder pattern — best when you want fluent, readable overrides in a test.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class UserData:
    username: str
    password: str
    email: str
    full_name: str
    marketing_opt_in: bool = False


@dataclass
class UserBuilder:
    """Fluent builder. Frozen output so a test can't mutate shared state."""

    _username: str = field(default_factory=unique_username)
    _password: str = "Str0ng!Passw0rd"
    _email: str = field(default_factory=unique_email)
    _full_name: str = field(default_factory=fake.name)
    _opt_in: bool = False

    def with_username(self, value: str) -> Self:
        self._username = value
        return self

    def with_password(self, value: str) -> Self:
        self._password = value
        return self

    def with_email(self, value: str) -> Self:
        self._email = value
        return self

    def opted_in(self) -> Self:
        self._opt_in = True
        return self

    def build(self) -> UserData:
        return UserData(
            username=self._username,
            password=self._password,
            email=self._email,
            full_name=self._full_name,
            marketing_opt_in=self._opt_in,
        )


# ---------------------------------------------------------------------------
# polyfactory — derives a factory straight from the pydantic model. Best for
# "give me a valid instance, I don't care about the values" and for fuzzing.
# ---------------------------------------------------------------------------
class ProductFactory(ModelFactory[Product]):
    __model__ = Product
    __use_defaults__ = True

    @classmethod
    def price(cls) -> float:
        return round(cls.__faker__.pyfloat(min_value=1, max_value=999, right_digits=2), 2)

    @classmethod
    def category(cls) -> str:
        return cls.__faker__.random_element(["audio", "input", "display", "video"])


# ---------------------------------------------------------------------------
# Named personas — for the handful of accounts that genuinely must pre-exist
# (SSO, payment-verified, KYC'd). Keep this list short; it is a liability.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Persona:
    username: str
    password: str
    description: str


PERSONAS = {
    "standard": Persona("alice", "wonderland", "Ordinary shopper, no special state"),
    "secondary": Persona("bob", "builder", "Second user — proves data isolation between accounts"),
}


def persona(name: str) -> Persona:
    try:
        return PERSONAS[name]
    except KeyError:
        raise KeyError(f"Unknown persona '{name}'. Known: {sorted(PERSONAS)}") from None


def variant(base: UserData, **overrides: object) -> UserData:
    """Derive a near-copy of an existing record — handy for boundary tables."""
    return replace(base, **overrides)  # type: ignore[arg-type]
