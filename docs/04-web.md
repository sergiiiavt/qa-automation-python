# Module 4 — Web UI testing with Playwright

## Why Playwright over Selenium in 2026

Not tribalism — specific, measurable differences:

| | Selenium 4 | Playwright |
|---|---|---|
| Waiting | Explicit waits you write | **Auto-waiting** built into every action |
| Isolation | New browser per test (slow) or shared state (risky) | **Browser contexts** — isolated, ~milliseconds |
| Network control | Requires a proxy | `page.route()` built in |
| Debugging | Screenshots, logs | **Trace viewer**: DOM snapshots, network, console, timeline |
| Mobile emulation | Manual UA/viewport | Device descriptors with touch, DPR, UA |
| Install | Manage drivers | `playwright install` |

Selenium remains the right answer when you need a browser Playwright doesn't
drive, a Grid you already run, or a huge existing suite. For a new project,
Playwright wins on the flakiness axis alone — and flakiness is the thing that
kills UI suites.

---

## Auto-waiting: the concept that eliminates 80% of flake

```python
page.get_by_test_id("submit").click()
```

Before clicking, Playwright waits for the element to be attached, visible,
stable (not animating), able to receive events (not covered), and enabled. If
any condition isn't met within the timeout, you get a failure that says *which*
one.

```python
expect(page.get_by_test_id("cart-count")).to_have_text("1")
```

`expect()` **retries** the assertion until it passes or times out. Compare:

```python
assert page.get_by_test_id("cart-count").inner_text() == "1"   # ✗ one shot, races
expect(page.get_by_test_id("cart-count")).to_have_text("1")     # ✓ retries
```

The first is the single most common source of flake in Playwright suites written
by people coming from Selenium. Use `expect()` for anything the app updates
asynchronously.

**`time.sleep` is banned.** If you want to sleep, the thing you actually need is
a *state* to wait for. The demo app stamps `data-loaded="true"` on the grid when
rendering completes, and the Page Object waits on that:

```python
expect(self.testid("product-grid")).to_have_attribute("data-loaded", "true")
```

Asking developers for a hook like this is a completely reasonable request and it
is worth more than any amount of clever waiting code.

---

## Locators, in priority order

1. **`get_by_role`** — what a user (and a screen reader) perceives.
   `page.get_by_role("button", name="Log in")`. Doubles as an accessibility
   signal: if `get_by_role` can't find it, assistive tech can't either.
2. **`get_by_test_id`** — `data-testid`. The only selector a redesign can't
   break. Configure the attribute once:
   ```python
   playwright.selectors.set_test_id_attribute("data-testid")
   ```
3. **`get_by_label` / `get_by_placeholder` / `get_by_text`** — good for forms and
   content, but couples to copy, which marketing will change.
4. **CSS** — acceptable for structural selection.
5. **XPath** — last resort. Brittle, unreadable, and slow on mobile.

Never: `.css-1x2y3z` (generated class names), `div > div > div:nth-child(3)`,
or anything containing an index.

### Chaining and filtering

```python
row = page.get_by_test_id("cart-row").filter(has_text="Aurora Headphones")
row.get_by_test_id("remove").click()
```

Scoped lookups beat global ones: they express the relationship, and they don't
break when a second matching element appears elsewhere on the page.

---

## Page Objects, done right

Read [framework/web/pages.py](../framework/web/pages.py) alongside this.

```python
class LoginPage(BasePage):
    path = "/login"
    ready_locator = "[data-testid=login-form]"

    @property
    def username(self) -> Locator:          # lazy: resolved at action time
        return self.testid("username")

    def login(self, username, password) -> "ProductsPage":   # intent + destination
        self.username.fill(username)
        self.password.fill(password)
        self.submit.click()
        return ProductsPage(self.page).wait_until_ready()
```

Four things to copy:

- **`ready_locator`** — a per-page definition of "loaded". Every `open()` waits
  on it, so no test ever starts against a half-rendered page.
- **Properties, not attributes** — a stored element handle goes stale on
  re-render; a `Locator` is just a description and never does.
- **Return the destination page** — the type checker then catches wrong chaining.
- **Separate methods for success and failure** — `login()` returns
  `ProductsPage`, `login_expecting_failure()` returns `LoginPage`. Never
  `-> LoginPage | ProductsPage`.

### Components

```python
products.card_for("Aurora Headphones").add_to_cart()
```

`ProductCard` is scoped to one card's root locator. Every repeated UI block with
its own behaviour deserves one. This is what stops Page Objects growing into
600-line classes with methods like `click_add_button_in_third_card`.

### Responsive: one Page Object, both layouts

```python
@property
def is_mobile_layout(self) -> bool:
    viewport = self.page.viewport_size
    return bool(viewport and viewport["width"] <= 640)

def open_nav(self):
    if self.is_mobile_layout:
        self.testid("menu-toggle").click()
```

Do **not** create a parallel `MobileHomePage` hierarchy for a responsive site.
Branch on the one thing that actually differs.

---

## Fixtures and speed

### storage_state — stop logging in 200 times

```python
context = browser.new_context(storage_state="artifacts/storage_state.gw0.json")
```

Log in once per worker through the real form, save cookies + localStorage,
inject into every context. Keep exactly **one** test that logs in through the
form — that one is testing login; the other 199 are testing something else.

Note it authenticates through the *UI form*, not by injecting a hand-made token.
Injecting is faster still, but it drifts from reality the day auth changes.

### Seed through the API, verify through the UI

```python
def test_removing_an_item_updates_the_total(app_as_user, api_seed):
    api_seed.cart.clear()                                # arrange: API, ~20 ms
    product = api_seed.products.first_in_stock()
    api_seed.cart.add_item(product.id, 2)

    cart = app_as_user.cart.open()                       # act + assert: UI
    cart.remove(product.name)

    approx_money(cart.total, 0.0)
```

Clicking through five screens to reach the screen under test is slow and couples
every test to every screen. This is the single biggest speed-up available to most
UI suites.

**The catch:** the API fixture and the browser must be the *same user*. That's
why `api_seed` takes `worker_account` — see [Module 6](06-test-data.md).

---

## Testing what only the UI can test

If a test's assertion could be made at the API layer, move it there. What is left
is genuinely UI work — and this is where the interesting tests are.

### Network interception: reaching the error paths

```python
page.route("**/api/cart/items", lambda route: route.fulfill(
    status=500, content_type="application/json", body='{"detail":"Internal error"}'))
```

Error branches are almost never tested manually and are almost always broken.
Playwright makes them one line. Also available: latency injection,
`context.set_offline(True)`, and modifying real responses in flight.

### Console errors

A silent JS exception is a defect the user hits tomorrow. The autouse
`_capture_on_failure` fixture in
[tests/web/conftest.py](../tests/web/conftest.py) hooks `page.on("console")` and
`page.on("pageerror")` and attaches them to the report.

### Visual and accessibility

Covered in
[tests/web/test_accessibility_and_visual.py](../tests/web/test_accessibility_and_visual.py):

- **axe** finds ~30–40% of WCAG issues. Gate on `serious`/`critical` only and
  ratchet down over time — gating on everything from day one on a legacy app
  produces a red build nobody can fix, and the job gets disabled within a week.
- **Visual regression** needs four levers or it will flake: no animations, a
  settled state, masked dynamic regions, a non-zero pixel threshold. All four
  are demonstrated. Baselines are **source** — they live in `tests/web/baselines/`
  and get reviewed in PRs, not in a gitignored output directory.

The dark-mode audit found a real contrast failure in this repo's own CSS
(white on `#6b9bff` is 2.7:1). Dark mode is a whole second theme that usually
gets zero coverage; running the same audit under `color_scheme="dark"` costs one
fixture.

---

## Debugging

```bash
pytest tests/web --headed --slowmo 500        # watch it happen
pytest tests/web --tracing retain-on-failure  # then: playwright show-trace trace.zip
PWDEBUG=1 pytest tests/web -k login           # Playwright Inspector, step through
playwright codegen http://127.0.0.1:8000      # record actions -> generated locators
```

**The trace viewer is the tool to learn.** It gives you a DOM snapshot at every
action, network activity, console output, and a timeline. Most "impossible" UI
failures become obvious in 30 seconds there. Use `codegen` to discover locators,
never to generate tests you keep — its output has no abstraction.

---

## Parallelism

```bash
pytest tests/web -n auto
```

Playwright contexts are isolated by construction, so this works — provided your
*data* is isolated too. That's [Module 6](06-test-data.md), and it's the part
people get wrong.

Browser-level parallelism in CI: use a matrix over `--browser=chromium|firefox|webkit`
with `fail-fast: false`, so one browser failing doesn't hide the others. See
[.github/workflows/ci.yml](../.github/workflows/ci.yml).

---

## Checkpoint

1. Why does `expect(locator).to_have_text("1")` behave differently from
   `assert locator.inner_text() == "1"`?
2. What are the five conditions Playwright checks before a click?
3. Why do Page Objects return the destination page?
4. When is a separate mobile Page Object justified, and when is it a mistake?
5. Name the four levers that make visual regression maintainable.

Next: [Module 5 — Mobile](05-mobile.md)
