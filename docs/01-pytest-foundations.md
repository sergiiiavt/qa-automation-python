# Module 1 — pytest foundations

Everything in this framework is built out of five pytest concepts. Get these
right and the rest is detail; get them wrong and no amount of Page Object
polish will save the suite.

---

## 1. Fixtures: setup, teardown, and dependency injection

A fixture is a named piece of setup that pytest injects by parameter name.

```python
@pytest.fixture
def api_client(base_url: str):
    with ApiClient(base_url=base_url) as client:
        yield client               # everything after yield is teardown
```

Fixtures **compose**. `cart_with_item` depends on `shop_as_user`, which depends
on `shop`, which depends on `api_client`, which depends on `base_url`, which
depends on `sut`. Requesting one fixture builds the whole chain, in order, and
tears it down in reverse.

> Read the real chain: [tests/services/conftest.py](../tests/services/conftest.py)

**Why `yield` and not `return` + a finalizer:** teardown sits next to setup, so
you can see both at once. This is the difference between a fixture you can review
and one you have to trace.

### The teardown rule that catches everyone

Teardown after `yield` **does not run** if the setup before `yield` raised. If
your setup can fail halfway, split it, or clean up defensively at the *start* of
the fixture too:

```python
shop.login_as(username, password)
shop.cart.clear()      # <- clean BEFORE, because the last run may have crashed
yield shop
shop.cart.clear()      # <- and after
```

That "clean before" line is in [tests/services/conftest.py](../tests/services/conftest.py)
for exactly this reason.

---

## 2. Scope: the decision that determines whether your suite works

| Scope | Created | Use for |
|---|---|---|
| `function` (default) | Once per test | Anything mutable. Default to this. |
| `class` | Once per test class | Rare; a shared expensive setup for a related group |
| `module` | Once per file | Read-only data loaded from disk |
| `session` | Once per run | Truly immutable + expensive: a server, a browser, a schema |

**With `pytest-xdist`, "session" means "once per worker."** Four workers means
four session setups. Anything session-scoped that mutates shared state is a bug
waiting for `-n auto`.

That is not a theoretical warning. This suite had exactly that bug:

```python
# The version that broke under -n 4
@pytest.fixture(autouse=True, scope="session")
def _reset_sut(base_url):
    httpx.post(f"{base_url}/api/testing/reset")   # wipes EVERY worker's state
```

Each worker's "once per session" reset detonated the other three workers'
sessions mid-run. The [fix](../tests/services/conftest.py) was to delete it and
give each worker its own account instead.

### Picking a scope, mechanically

> Is it expensive to create? → No: `function`, stop thinking.
> Yes → Can a test mutate it? → Yes: `function` anyway, or isolate it per worker.
> No (genuinely immutable) → `session`.

`ApiClient` is function-scoped in this framework even though it is cheap to
create, because it carries a token. A session-scoped client would leak an
authenticated session into a test that meant to be anonymous — an
order-dependent failure that only appears when someone reorders the file.

---

## 3. Parametrize: one test, many cases

```python
@pytest.mark.parametrize(
    ("quantity", "expected_status", "case"),
    [
        (1,   201, "minimum valid"),
        (99,  201, "maximum valid"),
        (0,   422, "below minimum"),
        (100, 422, "above maximum"),
        (1.5, 422, "non-integer"),
    ],
)
def test_quantity_boundaries(shop_as_user, quantity, expected_status, case):
    ...
```

Full version: [tests/services/test_cart_flow.py](../tests/services/test_cart_flow.py)

**Rules that make parametrize pay off:**

- **Carry a `case` label.** A failure reads `[below minimum]` instead of `[0-422]`.
- **One axis per parametrize.** Stacking two decorators gives you the cartesian
  product — usually more tests than you meant.
- **Table = boundaries, not samples.** Min, min−1, max, max+1, and the type
  boundary. The middle of a valid range almost never finds anything.
- **Stop when the bodies diverge.** If a row needs an `if`, it is a different test.

### Parametrizing a *fixture* instead

```python
@pytest.fixture(params=["iPhone 15", "Pixel 7", "Galaxy S9+"], ids=lambda d: d)
def mobile_page(request, playwright, browser): ...
```

Every test in the file now runs on every device. Adding a device is one line.
See [tests/web/test_mobile_web.py](../tests/web/test_mobile_web.py).

---

## 4. Markers: selecting what runs

Declared in [pyproject.toml](../pyproject.toml) under `markers`, enforced by
`--strict-markers` so a typo fails the run instead of silently selecting nothing.

```bash
pytest -m smoke                          # the gate
pytest -m "regression and not slow"      # boolean expressions work
pytest -m "web or mobile_web"
```

**Auto-mark by location** instead of hand-annotating hundreds of tests — see
`pytest_collection_modifyitems` in [conftest.py](../conftest.py). Markers stay
correct by construction and nobody forgets one.

### `xfail` vs `skip` — not interchangeable

| | Meaning | When it starts passing |
|---|---|---|
| `skip` | "Don't run this here" (wrong OS, no device) | Nothing happens — it silently rots |
| `xfail(strict=True)` | "Known bug, ticket #X" | **The build goes red**, forcing cleanup |

With `xfail_strict = true` set globally, an unexpected pass is a failure. That is
what stops the known-issues list from becoming permanent. The BOLA test in
[test_cart_flow.py](../tests/services/test_cart_flow.py) uses this: the build is
green today, and the day SHOP-114 is fixed the build turns red until someone
deletes the marker.

---

## 5. Hooks: framework-level behaviour

Hooks are pytest's extension points. Four in this framework, all in
[conftest.py](../conftest.py):

**`pytest_addoption`** — custom CLI flags (`--env`, `--no-sut`, `--platform`).

**`pytest_configure`** — runs after options are parsed. Writes
`environment.properties` for Allure so every report records which environment,
browser and build produced it.

**`pytest_collection_modifyitems`** — runs after collection, before execution.
Auto-marks by directory, and skips the mobile layer when no Appium server is
reachable. Skipping beats erroring: a developer without Appium can still run the
whole suite.

**`pytest_runtest_makereport`** — the important one:

```python
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, f"rep_{outcome.get_result().when}", outcome.get_result())
```

This publishes each phase's result onto the test item, which is the **only** way
a fixture's teardown can know whether the test passed:

```python
if getattr(request.node, "rep_call", None) and request.node.rep_call.failed:
    attach_png("failure-screenshot", page.screenshot())
```

Without it you either screenshot every test (gigabytes of noise) or none.

---

## 6. Configuration that keeps the suite honest

From [pyproject.toml](../pyproject.toml), with the reasoning:

```toml
addopts = ["-ra", "--strict-markers", "--strict-config", "--import-mode=importlib"]
xfail_strict = true
filterwarnings = ["error", ...]
```

- `-ra` — summarise every non-passing outcome. You want to see skips, not just failures.
- `--strict-markers` / `--strict-config` — typos become errors.
- `--import-mode=importlib` — modern imports; no `__init__.py` needed under `tests/`.
- `xfail_strict` — see above.
- `filterwarnings = ["error"]` — a deprecation warning today is a broken build in
  a year. Promote them now, while the fix is small. Each exemption must name a
  reason; a blanket ignore list is the same as not having one.

---

## Debugging pytest, fast

```bash
pytest --lf                     # last failed only
pytest --ff                     # failed first, then the rest
pytest -x                       # stop at the first failure
pytest --pdb                    # drop into a debugger at the failure
pytest --setup-show             # show fixture setup/teardown order
pytest --fixtures               # list every available fixture and its docstring
pytest --collect-only -q        # what would run, without running it
pytest -k "cart and not remove" # select by name substring
pytest --durations=10           # the ten slowest tests
```

`--setup-show` is the one people don't know about and should. When a fixture
misfires, it shows you the exact construction order.

---

## Checkpoint

You should be able to answer these without looking:

1. Why is `ApiClient` function-scoped when creating it is nearly free?
2. What does `session` scope mean under `pytest -n 4`?
3. Why does a fixture need `rep_call` to take a screenshot on failure?
4. When is `xfail` right and `skip` wrong?
5. What breaks if you stack two `@pytest.mark.parametrize` decorators?

Next: [Module 2 — Framework architecture](02-architecture.md)
