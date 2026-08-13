# Cheat sheet

## Running

```bash
pytest                              # everything
pytest tests/services -q            # one layer
pytest -m smoke                     # by marker
pytest -m "web and not slow"        # boolean marker expressions
pytest -k "cart and not remove"     # by name substring
pytest -n auto                      # parallel (xdist)
pytest --lf                         # last failed
pytest --ff                         # failed first
pytest -x                           # stop on first failure
pytest --pdb                        # debugger at the failure
pytest --setup-show                 # fixture setup/teardown order
pytest --fixtures                   # every available fixture + docstring
pytest --collect-only -q            # what would run
pytest --durations=10               # slowest tests
pytest --count=20 path::test        # repeat (pytest-repeat) — flake hunting
```

This framework's own flags:

```bash
pytest --env=stage
pytest --no-sut                     # don't start the bundled app
pytest --platform=ios
pytest --headed --slowmo 400        # pytest-playwright
pytest --browser=firefox
pytest --tracing retain-on-failure
pytest --alluredir=allure-results
```

## pytest

```python
@pytest.fixture(scope="session")          # function | class | module | session
@pytest.fixture(autouse=True)
@pytest.fixture(params=[...], ids=[...])

@pytest.mark.parametrize(("a", "b"), [(1, 2), (3, 4)])
@pytest.mark.skipif(cond, reason="...")
@pytest.mark.xfail(reason="TICKET-1", strict=True)
@pytest.mark.usefixtures("name")

pytest.raises(ValueError, match="pattern")
pytest.approx(0.3, abs=1e-9)
request.getfixturevalue("name")           # resolve a fixture dynamically
request.node.rep_call.failed              # did the test fail? (needs the hook)
```

## Playwright

### Locators (best first)

```python
page.get_by_role("button", name="Log in")
page.get_by_test_id("submit")
page.get_by_label("Email")
page.get_by_placeholder("Search")
page.get_by_text("Welcome", exact=False)
page.locator("css=.card").filter(has_text="Aurora")
page.locator("[data-testid=row]").nth(2)
parent.get_by_test_id("child")            # scoped
```

### Actions

```python
locator.click(force=False, position={"x":1,"y":1})
locator.fill("text")                      # prefer over type()
locator.press("Enter")
locator.select_option("audio")
locator.check() / .uncheck()
locator.hover() / .focus() / .scroll_into_view_if_needed()
locator.set_input_files("path.png")
page.keyboard.press("Tab")
```

### Assertions (auto-retrying)

```python
expect(locator).to_be_visible() / to_be_hidden()
expect(locator).to_have_text("x") / to_contain_text("x")
expect(locator).to_have_value("x") / to_have_attribute("k", "v")
expect(locator).to_have_count(3)
expect(locator).to_be_enabled() / to_be_disabled() / to_be_checked()
expect(page).to_have_url("...") / to_have_title("...")
expect(locator).not_to_be_visible()       # negation
```

### Context and network

```python
browser.new_context(**playwright.devices["iPhone 15"],
                    storage_state="state.json",
                    color_scheme="dark", locale="en-US", timezone_id="UTC")
context.set_offline(True)
page.route("**/api/x", lambda r: r.fulfill(status=500, body="{}"))
page.route("**/api/x", lambda r: r.abort())
page.on("console", handler); page.on("pageerror", handler)
page.wait_for_load_state("networkidle")
page.screenshot(full_page=True, mask=[locator])
```

## Appium (3.x / Python client 6.x)

```python
from appium.options.android import UiAutomator2Options
opts = UiAutomator2Options()
opts.platform_name, opts.device_name, opts.automation_name = "Android", "Pixel_7", "UiAutomator2"
opts.set_capability("appium:autoGrantPermissions", True)
driver = webdriver.Remote("http://127.0.0.1:4723", options=opts)
```

### Locators (best first)

```python
(AppiumBy.ACCESSIBILITY_ID, "login-button")
(AppiumBy.ID, "com.app:id/login")
(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("Log")')
(AppiumBy.IOS_PREDICATE, 'label CONTAINS "Log"')
(AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeButton[`name == "login"`]')
(AppiumBy.XPATH, "//*")                   # last resort
```

### Device control

```python
driver.background_app(5)
driver.orientation = "LANDSCAPE"
driver.back()
driver.set_network_connection(1)          # 1=airplane 4=data 6=all
driver.get_log("logcat")
driver.contexts; driver.switch_to.context("WEBVIEW_com.app")
driver.execute_script("mobile: swipeGesture", {...})
driver.execute_script("mobile: scrollGesture", {...})
driver.is_keyboard_shown(); driver.hide_keyboard()
```

### CLI

```bash
appium driver install uiautomator2
appium driver list --installed
appium --log appium.log
adb devices
adb logcat -c                             # clear before a run
adb shell dumpsys window | grep mCurrentFocus
```

## httpx

```python
client = httpx.Client(base_url="...", timeout=10, headers={...})
r = client.post("/path", json={...}, params={...})
r.status_code, r.json(), r.text, r.headers, r.elapsed
```

## pydantic v2

```python
class M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field: int = Field(ge=0, le=100)

M.model_validate(payload)                 # raises ValidationError
m.model_dump() / m.model_dump_json()
```

## Hypothesis

```python
@given(st.integers(min_value=1, max_value=99))
@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40))
@given(st.lists(st.integers(), min_size=1, max_size=5))
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
```

## Schemathesis 4

```python
schema = schemathesis.openapi.from_url("http://host/openapi.json")
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

@schema.parametrize()
def test(case):
    case.call_and_validate(excluded_checks=[positive_data_acceptance])
```

## Allure

```python
from framework.utils.reporting import step, attach_text, attach_png, label

with step("Place order"): ...
attach_text("request", body)
label(feature="Checkout", severity="critical", owner="qa")
```

```bash
allure serve allure-results
allure generate allure-results -o allure-report --clean
```

## This framework

```python
settings.api.base_url                     # typed config
shop.login_as(u, p).cart.add_item(id, 2)  # service objects
app.login.open().login(u, p)              # page objects -> destination page
soft(cond, "msg")                         # continue-on-failure assertion
approx_money(actual, expected)            # never == on money floats
eventually(lambda: check(), timeout=10)   # poll async backends
assert_matches_schema(payload, schema)    # JSON Schema
unique_username() / unique_email()        # xdist-safe uniqueness
persona("standard")                       # named pre-existing account
```

## Markers in this repo

`smoke` `regression` `services` `web` `mobile_web` `mobile_native` `contract`
`a11y` `slow` `flaky`

## Rules worth memorising

1. No `time.sleep` in a test. Ever.
2. Retry idempotent methods only.
3. A 500 on malformed input is always a bug.
4. `expect()` retries; `assert locator.inner_text()` does not.
5. Session scope means once **per xdist worker**.
6. Every test creates the data it needs.
7. Redact secrets before attaching them to a report.
8. `xfail(strict=True)` + a ticket, never a commented-out test.
9. Capture diagnostics before `driver.quit()`.
10. Push the test down a layer until it can no longer prove what you need.
