# Module 8 — Flakiness

> A flaky test is a test that passes and fails without the code changing.

Flakiness is the disease that kills automation programmes. Not slowness, not
coverage gaps — flakiness, because it destroys trust, and an untrusted suite
gets ignored, and an ignored suite gets deleted.

**The one rule: never "fix" a flaky test by retrying it.** A retry converts a
visible problem into an invisible one. Sometimes the flake is telling you about a
real race condition that your users will hit.

---

## The seven root causes

Diagnose before you touch anything. In practice, every flake is one of these.

### 1. Timing / race conditions — ~40% of flakes

**Symptom:** fails on slow machines, in CI, or under parallel load. Passes when
you watch it.

**Cause:** asserting before the app finished, or waiting for a *duration* instead
of a *state*.

```python
time.sleep(2)                                    # ✗ guesses
assert page.locator("#total").inner_text() == "$50.00"

expect(page.get_by_test_id("cart-total")).to_have_text("$50.00")   # ✓ retries until true
```

**Fix:** wait for state. Playwright's `expect()` retries; Appium's
`WebDriverWait` polls; for async backends use `eventually()` from
[framework/utils/assertions.py](../framework/utils/assertions.py).

**The best fix is a hook.** The demo app stamps `data-loaded="true"` when
rendering completes. Ask developers for these — it is a cheap request and it
removes a whole class of flake permanently.

### 2. Test interdependence — ~20%

**Symptom:** passes alone, fails in a suite. Order-dependent.

**Diagnose:**
```bash
pytest tests/services/test_cart_flow.py::test_add_item_to_empty_cart   # alone: green?
pytest tests -p randomly                                               # shuffled: red?
```

**Fix:** each test creates its own data ([Module 6](06-test-data.md)). Never
chain tests. If test B needs test A's outcome, make it a fixture.

### 3. Shared mutable state under parallelism — ~15%

**Symptom:** green sequentially, red with `-n auto`. Different tests fail each run.

This is the one that hit this repo. Four workers, one `alice`, one cart. See
[Module 6](06-test-data.md) for the full story and the three fixes.

**Diagnose:**
```bash
pytest tests -n 1     # green
pytest tests -n 4     # red, and the failures move around
```

Failures that *move between runs* are the signature.

#### A second, subtler version: shared *resources*, not just shared data

This repo hit it twice. The second time looked like an infrastructure blip:

```
httpcore.ConnectError: [WinError 10061] No connection could be made
```

The demo app was started by a `scope="session"` autouse fixture. Under `-n 4`
one worker won the race to bind the port and started the server as its child
process — then, the moment *its* last test finished, its fixture teardown killed
the server while the other three workers were still running. Roughly one run in
four went red, in whichever tests happened to be in flight.

The fix is not a retry. A resource shared by all workers must be owned by the
**controller**, not by a worker:

```python
def pytest_configure(config):
    if not hasattr(config, "workerinput"):   # controller, not a worker
        _start_sut(config)

def pytest_unconfigure(config):              # after every worker has finished
    _stop_sut(config)
```

Generalise it: ask of every session-scoped fixture, *"if four copies of this
run, and any one of them tears down first, what breaks?"*

#### And sometimes the flake is in your tooling

The third parallel flake in this repo was
`FailedHealthCheck: Too many generated examples are filtered out`, from
Hypothesis, on the only two API operations that take no parameters and no body.
With nothing to vary, the generator ran out of distinct examples and filtered
the duplicates — intermittently, because it depends on the random seed.

That is a fact about the generator meeting a tiny input space, not a fact about
the API. Suppressing that one health check, with the reason written next to the
code, is the correct fix. Knowing the difference between a finding about the
*system* and a finding about the *tool* is a large part of working with
generated tests.

### 4. Environment differences — ~10%

Timezone, locale, screen size, fonts, browser version, DST.

```python
"timezone_id": "UTC",     # in browser_context_args
"locale": "en-US",
```

**Fix:** pin everything, and run in a container.

### 5. Test data drift — ~5%

**Symptom:** worked for months, now fails. A record was deleted, a coupon
expired, a demo account's password rotated.

**Fix:** generate data rather than depending on it. When you must depend on it,
assert the precondition with a message that names the cause:

```python
assert products, "SUT has no in-stock products — fixture data is broken"
```

### 6. Genuine product bugs — ~5%

**The most valuable category, and the most often thrown away.** An intermittent
failure can be an intermittent *bug*: a real race in the application, a
connection-pool exhaustion, a cache invalidation gap.

Before quarantining anything, ask: *could a user hit this?* If the answer is
"yes, one time in fifty" — that is a defect report, not a flaky test.

### 7. Infrastructure — ~5%

Network blips, container OOM, disk full, rate limits.

**Fix:** bounded retry at the *transport* layer (which is why `ApiClient` retries
429/502/503/504 on idempotent methods only), plus resource limits in CI. Never
retry at the test level for this.

---

## The diagnostic procedure

```bash
# 1. Is it actually flaky, or just failing?
pytest path::test_name --count=20              # pytest-repeat

# 2. Order-dependent?
pytest path::test_name                          # alone
pytest tests -p randomly                        # shuffled

# 3. Parallel-only?
pytest tests -n 1  vs  pytest tests -n 4

# 4. Environment-dependent?
docker compose run tests pytest path::test_name

# 5. Slow-machine-dependent?
pytest path::test_name --slowmo 1000            # or throttle the network
```

Then read the evidence you already collect: screenshot, DOM, console, HTTP
log, trace. Most "impossible" failures are obvious in the Playwright trace
viewer within 30 seconds.

---

## Designing flake-resistant tests

**Assert on state, never on timing.**

**Prefer semantic locators.** `get_by_role("button", name="Log in")` survives a
redesign; `.css-1x2y3z` does not.

**One Act per test.** Long tests have more failure points and worse diagnostics.
A five-step journey is one test; a fifteen-step journey is a liability.

**Make the app tell you when it's ready.** `data-loaded`, a spinner that
actually disappears, a status region. Ask for it.

**Wait for the *right* state.** "Spinner gone" is not "data rendered". The gap
between them is where flakes live.

**Don't assert on things you don't control.** Ad iframes, third-party widgets,
timestamps, animation frames. Mask or stub them.

**Freeze time when the UI depends on it.**
```python
page.add_init_script("Date.now = () => 1700000000000;")
```

---

## Measuring flakiness

You cannot manage what you don't measure. Track:

- **Flake rate** = flaky runs ÷ total runs. Target < 1%. Above 5%, the suite is
  not trusted and you should stop adding tests until it's fixed.
- **Top 10 flaky tests** — Allure history gives you this directly.
- **Time-to-fix** for quarantined tests. If it exceeds two weeks, the process is
  broken, not the test.

A test that passes on rerun is flaky *by definition*. Log every one.

---

## The quarantine process

1. Test flakes → open a ticket immediately.
2. Mark it: `@pytest.mark.flaky` + `xfail(reason="FLAKE-231: ...", strict=False)`.
3. It keeps running, in a **non-blocking** job.
4. Two-week clock: fixed, or deleted.
5. Review the quarantine list every sprint.
6. Cap the list at ~2% of the suite. Past that, stop feature work.

A quarantined test that stops running is a deleted test with extra steps and a
false sense of coverage.

---

## Anti-patterns

| Anti-pattern | Why it's bad | Do instead |
|---|---|---|
| `time.sleep(5)` | Slow when it works, still fails when it doesn't | Wait for state |
| `--reruns 3` forever | Automates ignoring bugs | Fix the cause; use reruns to measure |
| `try/except: pass` around an action | Hides the failure | Handle the specific expected case |
| Increasing every timeout | Makes the suite slower and still flaky | Find the actual wait condition |
| Deleting the test | Loses the coverage *and* the signal | Quarantine with a ticket |
| "It's just flaky, rerun it" | Sometimes it's a real race | Diagnose first, every time |

---

## Checkpoint

1. A test passes alone and fails in the suite. Which two root causes, and how do
   you tell them apart?
2. Failures that move between tests under `-n 4` point at which cause?
3. Why is "genuine product bug" the most valuable flake category?
4. What is wrong with raising a timeout from 10 s to 60 s to fix a flake?
5. Your quarantine list is 12% of the suite. What do you do?

Next: [Module 9 — Strategy and metrics](09-strategy.md)
