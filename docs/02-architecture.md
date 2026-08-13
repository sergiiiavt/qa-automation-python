# Module 2 — Framework architecture

## The problem architecture solves

A test suite has a predictable lifecycle:

- **0–50 tests:** everything works. Any structure is fine.
- **50–200 tests:** duplication appears. Someone adds a `utils.py`. It becomes a
  dumping ground.
- **200–500 tests:** a UI change breaks 40 tests. Fixing them takes a week.
  Someone proposes a rewrite.
- **500+:** the suite is either well-layered or abandoned.

Architecture is what you do at test #10 so that test #400 costs the same to write
as test #4 did.

---

## The layers

```
       TESTS            what the system should do          tests/
         │                                                 (business language only)
         ▼
    PAGE / SCREEN / SERVICE OBJECTS                        framework/web, mobile, api
         │              how to operate the system          (intent-named methods)
         ▼
     DRIVER / TRANSPORT                                    framework/http, mobile/driver_factory
         │              how to talk to the system          (retries, waits, logging)
         ▼
   CONFIG · DATA · REPORTING                               framework/config, data, utils
                        cross-cutting concerns
```

### The one rule

**Each layer may only use the layer directly below it.**

A test never touches `httpx`. A Page Object never reads `os.environ`. A service
object never formats an Allure attachment. When you find yourself importing
sideways, you have found a missing abstraction.

### What goes where

| Layer | Contains | Never contains |
|---|---|---|
| `tests/` | Assertions, business flow, test data choices | Locators, URLs, HTTP verbs, waits |
| Page/Screen/Service objects | Locators, endpoints, intent methods | Assertions about business rules |
| Transport | Retries, timeouts, logging, redaction | Anything endpoint-specific |
| Config/Data/Reporting | Settings, factories, adapters | Test logic of any kind |

The most-violated cell is "Page Objects never contain assertions." The nuance:
a Page Object *may* assert its own **state** (`expect(form).to_be_visible()` in
`wait_until_ready`) — that is a precondition, not a verification. It must never
assert a **business rule** (`assert total == 42`), because then the test's
intent lives in two files.

---

## Reading the framework as a worked example

### Config — [framework/config.py](../framework/config.py)

```python
settings.api.base_url      # typed, autocompleted, validated at startup
```

Not `os.getenv("API_URL")`. The difference:

| | `os.environ` | Typed settings |
|---|---|---|
| Typo | `None` at 3 a.m. | Startup error |
| Type | Always `str` | `float`, `bool`, `Path`, enum |
| Discovery | grep the repo | Read one class |
| Defaults | Scattered `or "x"` | One place |

Layering (highest priority first): **env vars → `.env` → `config/<env>.yaml` →
field defaults.** One variable, `QA_ENV`, switches environments.

### Transport — [framework/http/client.py](../framework/http/client.py)

One class owns retries, timeouts, logging, and Allure attachments. Two details
worth stealing:

**Retry only idempotent methods.** `IDEMPOTENT_METHODS = {GET, HEAD, OPTIONS,
PUT, DELETE}`. A retried POST can create two orders or charge a card twice.
There is a test that enforces this — `test_api_client_does_not_retry_post` —
because "obviously nobody would do that" is not a guarantee.

**Redact secrets before they reach a report.** `_headers()` masks
`Authorization`, `Cookie`, `X-API-Key`. Allure attachments get uploaded, archived
and shared; a bearer token in one is a real incident.

### Service objects — [framework/api/shop.py](../framework/api/shop.py)

The API's equivalent of Page Objects. Note the deliberate two-method pattern:

```python
def add_item(self, product_id, quantity=1) -> Cart:          # happy path: typed
def add_item_raw(self, product_id, quantity=1) -> Response:  # negative: raw
```

One method that "sometimes parses and sometimes doesn't" is how this layer rots.
Negative tests need status codes and error bodies; positive tests need a model.
Different needs, different methods.

### Models — [framework/api/models.py](../framework/api/models.py)

The suite declares its **own** models rather than importing the server's.

Importing production models feels DRY and destroys the test's value: if a
developer renames a field, the shared model renames with it and every test still
passes. A separate declaration is what makes `extra="forbid"` meaningful — an
undocumented new field in a response becomes a visible, discussable change.

### Page Objects — [framework/web/base_page.py](../framework/web/base_page.py)

Three rules encoded in the base class:

1. **Locators are properties, not attributes.** A `Locator` is a lazy query
   description; storing a resolved element in `__init__` is what makes Page
   Objects go stale when the DOM re-renders.
2. **Intent methods, not click methods.** `login(user, pw)`, not
   `type_username` + `type_password` + `click_submit`.
3. **Navigation methods return the destination page.**
   `LoginPage(page).open().login(u, p)` returns a `ProductsPage`, so the test
   reads as a flow and the type checker catches wrong chaining.

**Components, not god classes.** `ProductCard` in
[framework/web/pages.py](../framework/web/pages.py) is scoped to one card's root
locator. Without it, you end up with
`click_add_to_cart_button_in_third_card()`. With it: `products.card_for("Aurora
Headphones").add_to_cart()`.

### Screen Objects — [framework/mobile/base_screen.py](../framework/mobile/base_screen.py)

Same shape as the web layer, different mechanics: view hierarchy instead of DOM,
`AppiumBy` instead of CSS, gestures instead of scrolling. The parallel structure
is intentional — someone who learned the web layer can read the mobile layer.

---

## Conftest layering

```
conftest.py                 SUT lifecycle, settings, hooks, worker accounts
├── tests/services/conftest.py    ApiClient, ShopApi, personas
├── tests/web/conftest.py         Playwright tuning, storage_state, Page Objects
└── tests/mobile/conftest.py      Appium driver, Screen Objects
```

Fixtures are inherited downward, never sideways. The payoff is concrete:
`pytest tests/services` runs in 11 seconds on a machine with no browsers and no
Appium installed, because nothing in the services path imports them.

**Corollary:** put an import inside the fixture function, not at module top, when
it belongs to an optional layer. `tests/mobile/conftest.py` imports
`create_driver` *inside* the fixture so that collection succeeds without Appium.

---

## Naming, and why it is architecture

Test names are the report. A stakeholder reading a CI summary sees only names.

```python
def test_1():                                          # useless
def test_cart():                                       # what about it?
def test_add_item():                                   # what should happen?
def test_adding_same_product_twice_increments_quantity()  # a specification
```

The pattern: `test_<subject>_<action>_<expected outcome>`. If you can't write
that sentence, you don't yet know what you're testing.

---

## The Arrange–Act–Assert shape

Every test in this repo is three visually separated blocks:

```python
def test_remove_item_updates_total(cart_with_item):
    shop, product = cart_with_item          # Arrange (mostly in fixtures)

    cart = shop.cart.remove_item(product.id)   # Act — exactly one action

    assert cart.line_for(product.id) is None   # Assert
    approx_money(cart.total, 0.0)
```

**One Act per test.** Two actions means two tests, or it means the first action
is really arrangement and belongs in a fixture. The blank lines are not
decoration — they are how a reader finds the Act in two seconds.

---

## Extension points to design in from day one

You will need these; adding them later is expensive.

| Need | Mechanism here |
|---|---|
| New environment | `config/<env>.yaml` + `QA_ENV` |
| New browser | `--browser` (pytest-playwright), matrix in CI |
| New device | one string in the `DEVICES` list |
| Real-device cloud | `_cloud_options()` in the driver factory |
| New reporter | `framework/utils/reporting.py` — one adapter, no test changes |
| Skip a layer | directory-based markers |

Each one is a single edit in a single place. That is the actual test of whether
your architecture works.

---

## Checkpoint

1. Why does the framework declare its own pydantic models instead of importing
   the server's?
2. Why are locators properties rather than attributes set in `__init__`?
3. Where does a wait belong — the test, the Page Object, or the driver? Why?
4. What breaks if `tests/services/conftest.py` imports from `framework/mobile`?

Next: [Module 3 — Services / API testing](03-services.md)
