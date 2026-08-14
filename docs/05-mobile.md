# Module 5 — Mobile: native apps and mobile web

## First, decide what you actually mean by "mobile testing"

Three different problems get called the same thing, and conflating them is the
most common mobile-automation mistake.

| | What it is | Tool | Speed | Finds |
|---|---|---|---|---|
| **Mobile web, emulated** | Your responsive site at a phone viewport with touch + mobile UA | Playwright device descriptors | ~1 s/test | Layout, touch targets, overflow, responsive breakpoints |
| **Mobile web, real device** | Your site in real Chrome/Safari on real hardware | Appium + browser session | ~20–60 s/test | Engine bugs, real keyboard/viewport behaviour, true performance |
| **Native / hybrid app** | An installed `.apk` / `.ipa` | Appium + UiAutomator2 / XCUITest | ~30–90 s/test | Everything app-specific |

## The strategy that works

```
every commit     emulated mobile web (Playwright)     2–3 min     ← 80% of mobile-web defects
nightly          real-device mobile web (Appium)      15–30 min   ← engine + hardware reality
nightly/release  native app smoke + device-only flows 20–45 min   ← what only a device can prove
```

Most teams get this backwards: they build an expensive device suite first, it
takes 40 minutes and flakes, and nobody runs it. Start at the top of that table.

---

## Mobile web with Playwright (cheap, fast, high yield)

```python
descriptor = playwright.devices["iPhone 15"]
context = browser.new_context(**descriptor, base_url=base_url)
```

The descriptor sets viewport, device scale factor, mobile user agent, touch
support and `is_mobile`. Parametrize the **fixture** so adding a device covers
the whole file:

```python
@pytest.fixture(params=["iPhone 15", "Pixel 7", "Galaxy S9+", "iPad (gen 7)"], ids=lambda d: d)
def mobile_page(request, playwright, browser, base_url, storage_state): ...
```

Full file: [tests/web/test_mobile_web.py](../tests/web/test_mobile_web.py)

### The five assertions worth writing first

**1. The breakpoint actually fires.**

```python
if width <= 640:
    expect(products.testid("menu-toggle")).to_be_visible()
    expect(products.testid("main-nav")).to_be_hidden()
```

**2. No horizontal overflow.** *The* mobile bug — one element wider than the
viewport, usually a table or an unbroken string. Invisible on desktop:

```python
overflow = page.evaluate(
    "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
assert overflow <= 1
```

**3. Touch targets ≥ 44×44 CSS px.** WCAG 2.2 (2.5.8) asks 24×24; iOS HIG and
Material both say 44–48. This test found a real defect in this repo: the
hamburger was 40×46, because `min-height` was set and `min-width` wasn't.

**4. Text ≥ 12px.** Reusing desktop CSS on a phone produces unreadable labels.

**5. The critical journey completes.** Same Page Objects as desktop — the only
mobile-specific step is `open_nav()`.

### Beyond the basics — all still free in emulation

- **Rotation:** swap the viewport dimensions. A reliable source of clipped
  headers and stuck modals that almost nobody tests.
- **Slow 3G:** CDP `Network.emulateNetworkConditions`. Surfaces missing loading
  states and races that a gigabit office connection hides completely.
- **Offline:** `context.set_offline(True)`. The requirement is modest and
  non-negotiable — don't render a blank white screen.

### What emulation genuinely cannot do

Be honest about this in your test plan:

- It is **desktop Chromium**, not iOS WebKit. Every iOS browser is Safari
  underneath; Safari-specific bugs are invisible here.
- No real scroll momentum, pinch-zoom, or soft-keyboard viewport resizing.
- No real font fallback, no real GPU behaviour, no real device performance.

Those five bullets are exactly what the nightly real-device run is for.

---

## Appium: the current state (Appium 3, Python client 6)

Most tutorials online are Appium 1.x and will actively mislead you.

### What changed

**`DesiredCapabilities` dicts are gone.** Use typed options objects:

```python
from appium.options.android import UiAutomator2Options

opts = UiAutomator2Options()
opts.platform_name = "Android"
opts.automation_name = "UiAutomator2"
opts.device_name = "Pixel_7_API_34"
opts.set_capability("appium:autoGrantPermissions", True)

driver = webdriver.Remote(command_executor="http://127.0.0.1:4723", options=opts)
```

They serialise to W3C capabilities and catch typos at construction rather than at
session start.

**Vendor capabilities need the `appium:` prefix.** Anything not in the W3C
standard set.

**Security-feature prefixes are mandatory in Appium 3.** `adb_shell` became
`uiautomator2:adb_shell`. Optional in 2.x, required in 3.x.

**Drivers are separate packages** (unchanged from 2.x, still surprises people):

```bash
npm install -g appium
appium driver install uiautomator2
appium driver install xcuitest
appium driver list --installed
```

**`TouchAction` is removed.** Use `mobile:` extension scripts:

```python
driver.execute_script("mobile: swipeGesture", {
    "left": 100, "top": 400, "width": 400, "height": 800,
    "direction": "up", "percent": 0.6,
})
```

These run natively on the device and are dramatically more reliable than
hand-rolled pointer sequences.

Reference implementation:
[framework/mobile/driver_factory.py](../framework/mobile/driver_factory.py)

---

## Locators on mobile

Priority order — and the gap between #1 and #4 is much larger than on the web,
because every XPath query serialises the **entire view hierarchy** over HTTP.

**1. Accessibility ID** — `content-desc` on Android, `accessibilityIdentifier`
on iOS. One locator, both platforms:

```python
(AppiumBy.ACCESSIBILITY_ID, "login-button")
```

Asking developers to add these is the single highest-ROI request a mobile QA
engineer can make. It costs them minutes and saves you a permanent tax.

**2. ID / resource-id** — stable, platform-specific.

**3. Native selector engines** — powerful and fast:

```python
(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceIdMatches(".*product_title")')
(AppiumBy.IOS_PREDICATE, 'label CONTAINS "Aurora"')
(AppiumBy.IOS_CLASS_CHAIN, '**/XCUIElementTypeButton[`name == "add"`]')
```

**4. XPath** — last resort. Slow *and* brittle. Never index-based
(`(//android.widget.TextView)[3]`).

### Handling platform differences

```python
ERROR = by_platform(
    (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceIdMatches(".*error_text")'),
    (AppiumBy.IOS_PREDICATE, 'name == "error-text"'),
)
```

Use it sparingly. If more than ~20% of a screen's locators need a platform
split, stop and go ask for shared accessibility ids instead — you are paying
interest on someone else's shortcut.

---

## Waits on mobile

```python
driver.implicitly_wait(0)   # and never touch it again
```

Mixing implicit and explicit waits produces genuinely unpredictable timeouts —
the two mechanisms compound in ways that are documented nowhere. Pick explicit
(`WebDriverWait` + `expected_conditions`) and stay there.
[framework/mobile/base_screen.py](../framework/mobile/base_screen.py) does this.

Mobile timeouts should be **larger** than web timeouts: app launch, emulator
warm-up, and animations are all slower. 15 s default, 60–120 s for session start.

---

## Session strategy: one driver per test

```python
@pytest.fixture
def driver(request):
    session = create_driver(...)
    try:
        yield session
    finally:
        # capture diagnostics BEFORE quitting — a quit session can't screenshot
        if getattr(request.node, "rep_call", None) and request.node.rep_call.failed:
            attach_png("failure-screenshot", session.get_screenshot_as_png())
            attach_text("page-source", session.page_source)
            attach_text("logcat", ...)
        session.quit()
```

A mobile session is the least stable resource in the stack. An OS dialog, a
crash, a lost adb connection — and every subsequent test in a shared session is
poisoned. Function scope costs 5–10 s per test and saves entire red builds.

**Capture before quit.** This is the most common reason mobile failures arrive
with no evidence attached.

---

## Hybrid apps and WebViews

A hybrid app renders part of its UI in a WebView. Inside it, mobile locators
stop working and *web* locators start working — the biggest gotcha in hybrid
testing.

```python
driver.switch_to.context(next(c for c in driver.contexts if "WEBVIEW" in c))
# now CSS selectors work
driver.switch_to.context("NATIVE_APP")
```

See `switch_to_webview` in `base_screen.py`.

---

## What to automate on a real device

**Yes — device-only behaviour, which is where mobile bugs actually live:**

- permissions dialogs, biometrics, push notifications, deep links
- **backgrounding** (`driver.background_app(5)`) — where apps lose state and crash
- **rotation** — on Android this destroys and recreates the Activity; anything
  not saved in `onSaveInstanceState` is gone
- **hardware back button** — no web equivalent, reliably breaks navigation stacks
- **network loss** (`driver.set_network_connection(1)`)
- the one or two critical revenue journeys

**No — push these down to the services layer:**

- business-rule permutations, validation tables, error message text

Those run in milliseconds at the API layer and take minutes on a device. A
device suite that tries to cover business rules will always be too slow to run
and too flaky to trust.

Reference: [tests/mobile/test_native_app.py](../tests/mobile/test_native_app.py)

---

## Local setup

```bash
# Android
# 1. Install Android Studio -> SDK + an AVD (Pixel 7, any recent API level)
adb devices                       # confirm the device is visible
npm install -g appium
appium driver install uiautomator2
appium                            # starts on http://127.0.0.1:4723

# iOS (macOS only)
appium driver install xcuitest
brew install carthage ios-deploy
xcrun simctl list devices
```

**Your AVD's name and OS version almost certainly won't match this doc's
examples**, and that's fine. Android Studio names and versions an AVD based on
whatever it currently recommends — that drifts over time (API 34 today, a
newer one next year) and isn't something this course controls. Check what you
actually got:

```bash
emulator -list-avds                                  # the real AVD name
adb shell getprop ro.build.version.release            # the real OS version
```

Then set `QA_MOBILE__DEVICE_NAME` in `.env` (note the `__` — nested settings
need it, a single `_` is rejected as an unknown top-level field, not silently
ignored). `QA_MOBILE__PLATFORM_VERSION` is deliberately left unset by default
(see `MobileSettings` in [framework/config.py](../framework/config.py)) —
it's a hard filter in Appium's device lookup, not a hint, so only set it if
you're disambiguating between multiple running emulators.

Then, with no extra download — the app is bundled at
[apps/mda-2.2.0-25.apk](../apps/mda-2.2.0-25.apk), Sauce Labs' MIT-licensed
"My Demo App" (see [apps/README.md](../apps/README.md)):

```bash
pytest tests/mobile -m smoke
```

Without a running Appium server the mobile tests **skip cleanly** — see
`pytest_collection_modifyitems` in [conftest.py](../conftest.py). A framework
that explodes on a laptop without Appium is a framework developers route around.

### Bringing the stack up after a reboot

Three long-running processes, each in its own terminal, started in this order:

```bash
# 1. Emulator — wait for it to fully boot before continuing
emulator -avd <your-avd-name>
adb devices                       # confirm "device", not "offline"

# 2. Appium server
appium

# 3. Tests — the bundled FastAPI demo app (`sut`) starts itself automatically,
#    nothing else to run first
pytest tests/mobile -m smoke
```

Nothing else needs redoing after a restart — `.env` and your IDE's interpreter
selection both persist.

### Finding real locators: Appium Inspector

Every locator this course ships was found the same way you will find your
own — not guessed, not copied from a tutorial written for a different app:

```bash
appium                                    # server running in one terminal
npx @appium/inspector                     # or the desktop app, in another
```

Point Inspector at the same capabilities `driver_factory.py` builds (same
`app` path, same `platformName`/`deviceName`), start a session, and click an
element to see its resource id, content-desc, class and full attribute set.
That is genuinely the whole workflow — `framework/mobile/screens.py`'s
`LoginScreen`, `MenuScreen` and `CatalogScreen` were built exactly this way
against the bundled app. The product-detail, add-to-cart and checkout screens
were deliberately left unmodelled so Exercise 22b in
[Module 10](10-exercises.md) asks you to do this yourself rather than read
locators someone else already found.

### The full pipeline: a real build stage, not just a bundled binary

`apps/mda-2.2.0-25.apk` is a *binary*, committed so `pytest tests/mobile`
works offline in seconds with nothing else installed — consistent with every
other layer of this course. But a binary sitting in git is not a build
pipeline, and "mobile testing" in a real job usually means the whole chain:
compile the app, install the fresh build onto a target, test it, gate on the
result. The `build-mobile-app` job in
[.github/workflows/ci.yml](../.github/workflows/ci.yml) closes that gap for
real, nightly:

```
build-mobile-app                          mobile
┌─────────────────────────────┐          ┌──────────────────────────────┐
│ checkout my-demo-app-android │          │ download the freshly-built   │
│ at the pinned 2.2.0 commit   │  ──────▶ │ apk (not apps/mda-*.apk)     │
│ ./gradlew app:assembleDebug  │ artifact │ boot an emulator, install it,│
│ upload app-debug.apk         │          │ run pytest tests/mobile      │
└─────────────────────────────┘          └──────────────────────────────┘
```

Three things worth noticing:

**Pinned, not floating.** The checkout targets an exact commit SHA — the one
tagged `2.2.0` upstream, which is the release that produced the file
literally named `mda-2.2.0-25.apk`. Building against that repository's
default branch instead would let upstream change the app at any time, with
no diff in *this* repository to review, and silently break every locator in
`framework/mobile/screens.py`. Pin the thing your tests were verified
against, not "whatever is newest."

**Mirrored, not guessed.** The JDK version, the Android SDK setup action, and
the `./gradlew app:assembleDebug` command were copied from that repository's
own `.github/workflows/publish-on-release.yml` — the workflow that produced
the exact apk this course bundles — rather than assembled from a generic
Android CI tutorial. An old (2021-era) Gradle/AGP toolchain like this one is
worth treating as fragile until proven otherwise; the proof here is "this
exact command, on this exact commit, is what the app's own maintainers use."

**The `mobile` job now depends on `build-mobile-app`** and installs *that*
artifact, via `QA_APP_PATH`, instead of the committed reference binary. If
the build breaks, the pipeline reports that at the build stage — fast,
specific — rather than the test job failing forty minutes later with a
confusing "could not install app" error, which is what happens when a build
problem is only discovered downstream.

### Device clouds

BrowserStack, Sauce Labs, LambdaTest. The driver factory already handles it:

```python
opts.set_capability("bstack:options", {"userName": ..., "accessKey": ..., "buildName": ...})
```

The test never knows whether it runs on a local emulator or a device farm. That
indifference is the entire point of a driver factory.

**Choose devices from your analytics, not from the shelf.** The right matrix is
usually: newest flagship, a two-to-three-year-old mid-range (what most users
actually hold), the smallest supported screen, and the oldest supported OS.

---

## Emulator/simulator vs. real device

| | Emulator | Real device |
|---|---|---|
| Cost | Free | Hardware or cloud minutes |
| Speed | Fast on x86_64 + KVM | Slower |
| Finds | Logic, layout, navigation | Performance, thermals, camera, biometrics, real network |

Emulators for the bulk of CI; real devices for release gates and anything
sensor-related. In CI, enable KVM — without it, the emulator is ~10× slower.
See the `mobile` job in [.github/workflows/ci.yml](../.github/workflows/ci.yml).

---

## Checkpoint

1. Name three mobile-web defects emulation finds and two it structurally cannot.
2. Why is `implicitly_wait(0)` set and never changed?
3. Why is the Appium driver fixture function-scoped rather than session-scoped?
4. Why capture diagnostics before `driver.quit()`?
5. Which of these belongs on a real device: "discount code validation rules", or
   "cart survives backgrounding"? Why?

Next: [Module 6 — Test data](06-test-data.md)
