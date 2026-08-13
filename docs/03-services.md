# Module 3 — Services / API testing

The highest-value layer in almost every project. API tests are 50–200× faster
than UI tests, they don't flake for rendering reasons, and they can reach states
the UI cannot produce. If you only have time to build one layer well, build this
one.

---

## What belongs here

| Test it here | Test it in the UI |
|---|---|
| Business rules, calculations, totals | That the UI *shows* the total |
| Validation and boundary values | That an error message is *visible* |
| Authentication and authorization | That login redirects |
| Error responses (4xx/5xx) | That errors are rendered |
| Data integrity across endpoints | Layout, responsiveness, accessibility |
| Performance of individual endpoints | Perceived load behaviour |

The rule: **push a test down until it can no longer prove what you need.**

---

## Building the client

Start with [framework/http/client.py](../framework/http/client.py).

### The `expect=` parameter

This pattern is worth internalising:

```python
response = self.client.post(path, json=payload, expect=201)
```

It collapses the two-line `assert response.status_code == 201` idiom into the
call, and on failure raises `ApiError` — which subclasses `AssertionError`, so
pytest reports it as a **failure**, not an **error**. That distinction matters in
reports: failures are product problems, errors are infrastructure problems, and
conflating them makes triage slower.

The message includes method, URL, expected, actual and body:

```
POST http://127.0.0.1:8000/api/cart/items -> 409 (expected 201)
{"detail":"Product 4 is out of stock"}
```

### Retries, carefully

```python
IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}
RETRYABLE_STATUS   = {429, 502, 503, 504}
```

Never blanket-retry. A retried POST duplicates orders. And note what is *not*
retried: `500`. A 500 is a bug, not a blip — retrying it hides the defect you
were hired to find.

Retry logic is itself tested, with `respx` mocking the transport:
`test_api_client_retries_transient_5xx_on_idempotent_requests` and
`test_api_client_does_not_retry_post` in
[test_contract_and_properties.py](../tests/services/test_contract_and_properties.py).

### Redaction

```python
SENSITIVE = {"authorization", "cookie", "set-cookie", "x-api-key"}
```

Reports get archived and shared. Redact before attaching, not after.

---

## Service objects

[framework/api/shop.py](../framework/api/shop.py) — one class per resource, plus
a `ShopApi` facade so tests hold one object instead of four fixtures.

```python
shop.login_as("alice", "wonderland")
shop.cart.add_item(product.id, 2)
order = shop.orders.create()
```

Add convenience methods that express **intent about data**, not just endpoints:

```python
def first_in_stock(self) -> Product:
    products = self.list(in_stock=True)
    assert products, "SUT has no in-stock products — fixture data is broken"
    return products[0]
```

That assertion message is doing real work. When the demo data changes, twenty
tests fail with "fixture data is broken" instead of `IndexError: list index out
of range`.

---

## Validation strategy: three tools, three jobs

### 1. pydantic — models you own

```python
class Cart(Strict):
    items: list[CartLine]
    total: float
    currency: str
```

`Strict` sets `extra="forbid"` and `frozen=True`. Forbidding extras is the
aggressive choice and the right default for tests: an undocumented new field is
exactly the drift you want to hear about. Frozen means a test can't accidentally
mutate a shared response object.

`Cart.model_validate(response.json())` is a full structural assertion in one
line — types, required fields, ranges, and no surprises.

### 2. JSON Schema — contracts you don't own

```python
assert_matches_schema(payload, {"type": "array", "items": PRODUCT_SCHEMA})
```

Use this when the schema is an artefact you *receive* — a partner API, a file in
a schema registry. It also catches things a permissive pydantic model lets
through: `additionalProperties: false`, enums, cross-field constraints.
See [framework/utils/assertions.py](../framework/utils/assertions.py).

### 3. Schemathesis — the spec tests itself

```python
schema = schemathesis.openapi.from_asgi("/openapi.json", sut_app)

@schema.parametrize()
def test_api_conforms_to_its_openapi_spec(case):
    case.call_and_validate()
```

One generated test per operation; Hypothesis fills in the inputs. Built-in
checks: `not_a_server_error`, `status_code_conformance`,
`content_type_conformance`, `response_schema_conformance`,
`positive_data_acceptance`.

**Loading from the ASGI app rather than a URL** means collection never needs a
running server — the schema-driven tests stay collectable offline.

#### What it actually found here

Three findings from the first runs, and the triage is the lesson:

| Finding | Verdict | Action |
|---|---|---|
| Undocumented `400`/`401` | **Real** | The service returns them and the spec didn't say so → documented them in `sut/app.py` |
| `422` body shape mismatch | **Real, self-inflicted** | The fix above declared `detail: string`; FastAPI returns a list of error objects → removed the wrong override |
| `?in_stock=null` rejected | **Not a bug** | An optional query param is `boolean\|null` in the schema, but a query string cannot express JSON `null`. A limitation of OpenAPI, not a defect → check excluded, **with the reason written next to the code** |

That third row is the professional skill: tools produce findings, humans produce
verdicts. And an exclusion without a recorded reason is how a contract job decays
into a permanently-yellow build everyone ignores.

---

## Property-based testing

Example-based testing checks the cases you thought of. Property-based testing
hunts for the ones you didn't, then **shrinks** the counterexample to the
smallest input that still fails.

```python
@given(quantities=st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=4))
def test_cart_total_always_equals_sum_of_lines(shop_as_user, quantities):
    ...
```

Good properties are invariants, not examples:

- *round-trip*: `get(create(x)) == x`
- *invariance*: total always equals the sum of lines
- *idempotence*: deleting twice equals deleting once
- *never crashes*: any string in the search box returns 2xx
- *symmetry*: `in_stock=true` plus `in_stock=false` equals everything

### `@given` vs `parametrize`

| | Use |
|---|---|
| `parametrize` | A fixed, curated list — boundary tables, known injection payloads. One test id per row; works with function-scoped fixtures. |
| `@given` | Inputs you did *not* think of. Costs setup discipline. |

Both appear in
[test_contract_and_properties.py](../tests/services/test_contract_and_properties.py),
side by side, with a comment explaining the choice.

**The health-check trap:** Hypothesis warns when a `@given` test uses a
function-scoped fixture, because the fixture is *not* reset between generated
examples. Suppressing that warning means you have taken responsibility for
isolation yourself — which is why the property test above calls
`shop_as_user.cart.clear()` as its first line.

---

## Test design: what to actually write

For each endpoint, work through this list. It takes ten minutes and it is more
systematic than anyone's intuition.

**Happy path** — the documented behaviour, with a typed response.

**Boundaries** — min, min−1, max, max+1, type boundary. Skip the middle.

**Negative input** — empty body, missing required field, wrong types, oversized
values, wrong content type. Every one of these must return 4xx. **A 500 on bad
input is always a bug**, because it means the input reached code that didn't
expect it.

**Authorization** — the matrix that finds the expensive bugs:

| | Anonymous | Wrong user | Right user | Admin |
|---|---|---|---|---|
| Read own | 401 | 403/404 | 200 | 200 |
| Read other's | 401 | **403/404** | 403/404 | 200 |
| Modify other's | 401 | **403/404** | 403/404 | 200 |

The bold cells are **BOLA/IDOR** — OWASP API Security's #1 risk, and a three-line
test. This suite has one, and it *fails*: see the `xfail(strict=True)` on
`test_order_belongs_to_its_owner`.

**Idempotence** — call DELETE twice, PUT twice. Second call must not 404 or 500.

**Cross-endpoint consistency** — does `GET /products/1` return the same object as
the entry in `GET /products`? Two code paths serving one entity drift constantly.

**Isolation** — two users, two sessions, prove they cannot see each other's data.

---

## Mocking: when, and when not

| Situation | Approach |
|---|---|
| Testing *your* framework's transport logic | `respx` — mock httpx (see the retry tests) |
| A third-party dependency you don't control (payments, SMS) | Mock or use the vendor's sandbox |
| Your own service | **Don't mock.** You are testing the real thing; that is the point |

The failure mode to avoid: mocking so much that the test passes while the
integration is broken. If a test would still pass after you delete the service,
it isn't an API test.

---

## Performance signals, for free

You already have timing data. Use it:

```python
assert response.elapsed.total_seconds() < 1.0
```

This is not load testing — it is a canary. A single endpoint going from 80 ms to
900 ms on a normal build is worth knowing before it reaches a load test.
`--durations=10` is already in `addopts`; watch the trend across runs.

For real load testing, reach for **Locust** or **k6**, and drive it against the
same service objects where possible.

---

## Checkpoint

1. Why is `500` deliberately excluded from `RETRYABLE_STATUS`?
2. Why does the framework define its own models instead of importing the app's?
3. When would you choose JSON Schema over pydantic?
4. Write the BOLA test for a `GET /api/invoices/{id}` endpoint.
5. Which Schemathesis finding above was *not* a defect, and how did you decide?

Next: [Module 4 — Web UI with Playwright](04-web.md)
