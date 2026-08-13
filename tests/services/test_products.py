"""Products: filtering, search, and schema conformance."""

from __future__ import annotations

import pytest

from framework.api.shop import ShopApi
from framework.utils.assertions import assert_matches_schema, soft


@pytest.mark.smoke
def test_product_catalogue_is_not_empty(shop: ShopApi) -> None:
    products = shop.products.list()

    assert len(products) > 0
    assert len({p.id for p in products}) == len(products), "Duplicate product ids in catalogue"


def test_get_product_by_id_matches_list_entry(shop: ShopApi) -> None:
    """Cross-endpoint consistency. Two endpoints serving the same entity from
    different code paths drift constantly; this catches it in one assertion."""
    from_list = shop.products.list()[0]

    from_detail = shop.products.get(from_list.id)

    assert from_detail == from_list


@pytest.mark.parametrize("category", ["audio", "input", "display", "video"])
def test_filter_by_category_returns_only_that_category(shop: ShopApi, category: str) -> None:
    products = shop.products.list(category=category)

    assert products, f"No products in category '{category}'"
    offenders = [p for p in products if p.category != category]
    assert not offenders, f"Filter leaked other categories: {offenders}"


def test_filter_by_category_is_a_subset_of_the_full_catalogue(shop: ShopApi) -> None:
    """Relational assertion — stronger than hardcoding counts, and it survives
    the catalogue growing. Prefer invariants over magic numbers."""
    everything = {p.id for p in shop.products.list()}
    audio = {p.id for p in shop.products.list(category="audio")}

    assert audio <= everything
    assert 0 < len(audio) < len(everything)


@pytest.mark.parametrize(
    ("query", "expected_substring"),
    [("aurora", "Aurora"), ("AURORA", "Aurora"), ("phone", "Headphones"), ("  ", None)],
)
def test_search_is_case_insensitive_substring_match(
    shop: ShopApi, query: str, expected_substring: str | None
) -> None:
    results = shop.products.list(q=query)

    if expected_substring:
        assert results, f"Search '{query}' returned nothing"
        assert all(expected_substring.lower() in p.name.lower() for p in results)
    else:
        # Whitespace-only search: whatever the product decision is, pin it down.
        assert isinstance(results, list)


def test_search_with_no_matches_returns_empty_list_not_error(shop: ShopApi) -> None:
    """A 404 for "no results" is a classic API design mistake — an empty
    collection is not a missing resource. Worth asserting explicitly."""
    response = shop.client.get("/api/products", params={"q": "zzzz-no-such-product"})

    assert response.status_code == 200
    assert response.json() == []


def test_in_stock_filter_partitions_the_catalogue(shop: ShopApi) -> None:
    in_stock = shop.products.list(in_stock=True)
    out_of_stock = shop.products.list(in_stock=False)
    everything = shop.products.list()

    soft(all(p.in_stock for p in in_stock), "in_stock=true returned out-of-stock items")
    soft(not any(p.in_stock for p in out_of_stock), "in_stock=false returned in-stock items")
    soft(
        len(in_stock) + len(out_of_stock) == len(everything),
        "Partitions do not sum to the full catalogue — an item is in neither",
    )


@pytest.mark.parametrize(
    ("limit", "expected_status"),
    [(1, 200), (100, 200), (0, 422), (-5, 422), (101, 422), ("many", 422)],
)
def test_limit_parameter_boundaries(shop: ShopApi, limit: object, expected_status: int) -> None:
    response = shop.client.get("/api/products", params={"limit": limit})

    assert response.status_code == expected_status


def test_limit_caps_the_result_size(shop: ShopApi) -> None:
    assert len(shop.products.list(limit=2)) <= 2


@pytest.mark.parametrize("product_id", [999999, 0, -1])
def test_unknown_product_returns_404(shop: ShopApi, product_id: int) -> None:
    response = shop.products.get_raw(product_id)

    assert response.status_code == 404
    assert str(product_id) in response.json()["detail"]


def test_non_numeric_product_id_returns_422_not_500(shop: ShopApi) -> None:
    response = shop.products.get_raw("not-a-number")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Schema-level checks
# ---------------------------------------------------------------------------
PRODUCT_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "category", "price", "in_stock", "rating"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "name": {"type": "string", "minLength": 1},
        "category": {"type": "string", "enum": ["audio", "input", "display", "video"]},
        "price": {"type": "number", "minimum": 0},
        "in_stock": {"type": "boolean"},
        "rating": {"type": "number", "minimum": 0, "maximum": 5},
    },
}


@pytest.mark.contract
def test_every_product_matches_the_published_schema(shop: ShopApi) -> None:
    """Raw JSON Schema, deliberately *not* pydantic.

    Use this style when the schema is an artefact you receive (a partner spec, a
    file in a schema registry) rather than a model you maintain. It also catches
    things pydantic models often let through — here, `additionalProperties: false`
    and the category enum.
    """
    payload = shop.client.get("/api/products", expect=200).json()

    assert_matches_schema(payload, {"type": "array", "items": PRODUCT_SCHEMA})


@pytest.mark.contract
def test_openapi_declares_every_endpoint_the_tests_use(openapi_schema: dict) -> None:
    """Documentation drift check. If an endpoint the suite exercises disappears
    from the spec, someone changed the contract without updating the docs."""
    used = {
        "/api/auth/login",
        "/api/products",
        "/api/products/{product_id}",
        "/api/cart",
        "/api/cart/items",
        "/api/orders",
    }

    missing = used - set(openapi_schema["paths"])

    assert not missing, f"Endpoints under test are absent from the OpenAPI spec: {missing}"
