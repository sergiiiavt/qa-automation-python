# Module 6 — Test data

Test data causes more flakiness than every timing issue combined. It is also the
least-taught topic in automation. This module is short because the rules are
short — and it is the most important module in the course.

---

## The war story from this repo

The suite was green. Then:

```bash
$ pytest tests -n 4
FAILED tests/services/test_cart_flow.py::test_add_item_to_empty_cart
FAILED tests/services/test_cart_flow.py::test_adding_same_product_twice_increments_quantity
FAILED tests/services/test_cart_flow.py::test_cart_total_is_sum_of_line_totals
3 failed, 148 passed
```

Sequentially: green. In parallel: three failures. No timing bug, no race in the
app. **All four workers logged in as `alice` and mutated the same server-side
cart.** Worker 2's `add_item` landed in the cart worker 1 was asserting on.

This is the single most common "works locally, flaky on CI" story in the
industry, and the reflex fix — adding a retry — would have made it worse: it
would have hidden a real isolation defect behind a longer, more expensive,
still-wrong build.

### The three fixes, in order of preference

**1. Isolate the data.** One account per worker. Keeps full parallelism.
Requires the backend to support self-service creation:

```python
@pytest.fixture(scope="session")
def worker_account(base_url, worker_id) -> tuple[str, str]:
    username = f"qa_{worker_id}_{uuid.uuid4().hex[:8]}"
    httpx.post(f"{base_url}/api/auth/register", json={...})
    return username, password
```

**2. Isolate the state.** A per-test tenant, org, or namespace, if the product
has that concept. Often better than #1 for multi-tenant SaaS.

**3. Serialise.** `pytest-xdist --dist loadgroup` plus
`@pytest.mark.xdist_group("cart")` pins related tests to one worker. Correct,
but it caps your parallelism. A last resort, not a first response.

The fix here was #1 — plus adding `POST /api/auth/register` to the SUT.
**Asking the backend for a test-data creation endpoint is a legitimate,
high-leverage request.** It is usually an afternoon of work and it unblocks
parallelism permanently.

### The second bug the same run exposed

```python
@pytest.fixture(autouse=True, scope="session")
def _reset_sut(base_url):
    httpx.post(f"{base_url}/api/testing/reset")
```

"Session" scope means **once per worker**. Four workers, four resets, each one
detonating the other three workers' live sessions. A global reset is
fundamentally incompatible with parallel execution. It was deleted; the comment
explaining why is still in
[tests/services/conftest.py](../tests/services/conftest.py).

---

## The four rules

### 1. Every test creates the data it needs

Shared golden records are the #1 cause of order-dependent failures. If test A
must run before test B, you have a bug in your test design, not a scheduling
problem.

**Test it:** `pytest -p no:randomly tests` vs `pytest tests --randomly-seed=1234`
(with `pytest-randomly`). If order matters, data is shared.

### 2. Unique by construction

```python
def unique_suffix() -> str:
    worker = os.getenv("PYTEST_XDIST_WORKER", "gw0")
    return f"{worker}-{uuid.uuid4().hex[:8]}"
```

Worker-aware **and** run-aware. Any field with a uniqueness constraint gets one.
Timestamps alone are not enough — two workers can hit the same millisecond.

### 3. Specify only what the test is about

```python
user = UserBuilder().with_email("boundary@example.test").build()
```

Everything else is generated. **When a test names a value, that value should be
load-bearing for the assertion.** Otherwise it is noise that every future reader
has to check for relevance.

### 4. Clean up before, not just after

```python
shop.cart.clear()    # BEFORE — the last run may have crashed mid-test
yield shop
shop.cart.clear()    # after
```

Teardown after `yield` does not run if setup raised. Defensive cleanup at the
start makes the suite recoverable.

---

## The four generation patterns

From [framework/data/factories.py](../framework/data/factories.py).

### Builder — fluent, readable overrides

```python
@dataclass
class UserBuilder:
    _username: str = field(default_factory=unique_username)
    _password: str = "Str0ng!Passw0rd"

    def with_email(self, value) -> Self: ...
    def build(self) -> UserData: ...
```

Best when tests care about *specific* fields. The frozen output means a test
can't mutate shared state.

### Factory from a model — polyfactory

```python
class ProductFactory(ModelFactory[Product]):
    __model__ = Product

    @classmethod
    def price(cls) -> float:
        return round(cls.__faker__.pyfloat(min_value=1, max_value=999, right_digits=2), 2)

product = ProductFactory.build()          # valid instance, values you don't care about
```

Best for "give me something valid" and for fuzzing. Derived from the pydantic
model, so it can never drift from the schema.

### Personas — the few accounts that must pre-exist

```python
PERSONAS = {
    "standard":  Persona("alice", "wonderland", "Ordinary shopper"),
    "secondary": Persona("bob", "builder", "Proves data isolation between accounts"),
}
```

For state you genuinely cannot create per test: SSO accounts, KYC-verified
users, payment-method-on-file. **Keep this list short — it is a liability.**
Every persona is shared mutable state waiting to bite you in parallel.

Use them for *read-only* scenarios (login tests), never for tests that mutate.
That distinction is exactly why `test_login_with_valid_credentials` still uses
`persona("standard")` while every cart test uses `worker_account`.

### Fixture files — for large, static reference data

YAML/JSON in the repo for things like tax tables or country lists. Load them
module-scoped (read-only, so scope is safe) and treat them as source.

---

## Faker, deterministically

```python
Faker.seed(int(os.getenv("QA_FAKER_SEED", "0")) or None)
```

Unseeded by default — variety finds bugs. Seed it when reproducing a specific
failure: `QA_FAKER_SEED=42 pytest -k the_failing_test`.

Always use `.test`, `.example` or `.invalid` domains for generated emails. RFC
2606 reserves them; using a real domain means your test suite eventually emails
a stranger.

---

## Cleanup strategies

| Strategy | Use when | Watch out |
|---|---|---|
| Fixture teardown | Default | Doesn't run if setup raised |
| Unique data, never clean | Data is cheap and namespaced | The database grows forever |
| Scheduled sweeper | Shared long-lived environments | Must match your uniqueness prefix |
| Transaction rollback | You control the DB session | Only works for in-process tests |
| Global reset endpoint | **Sequential runs only** | Detonates parallel runs — see above |

Whatever you choose, cleanup must be **idempotent** and must never fail the test
it belongs to. A cleanup error is a warning; the test result already happened.

---

## Environment-specific data

```yaml
# config/local.yaml
user:
  name: alice
  password: wonderland
```

Never hardcode credentials in tests. Never commit real ones. `.env` is
gitignored; `.env.example` documents the shape. In CI use secrets; in
staging/prod use a vault.

---

## Checkpoint

1. Three cart tests pass alone and fail under `-n 4`. Name the three fixes in
   order of preference, and say why "add a retry" is not on the list.
2. Why is a session-scoped global reset incompatible with xdist?
3. When is a persona appropriate and when is it a trap?
4. Why does `unique_suffix()` include the worker id *and* a UUID?
5. Why clean up before `yield` as well as after?

Next: [Module 7 — CI and reporting](07-ci-reporting.md)
