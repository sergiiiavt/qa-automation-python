# Module 7 — CI and reporting

A test suite nobody runs has negative value: it costs maintenance and returns
nothing. This module is about making the suite run automatically and produce
evidence people act on.

---

## Pipeline shape

```
push / PR   →  lint  →  services (40 s)  →  web × 3 browsers (8 min)  →  report
nightly     →  the above + real devices + long property-based runs
```

**Fast layers gate slow ones.** There is no point spending eight minutes on
browsers when a 40-second API run already proved the build is broken.

Full pipeline: [.github/workflows/ci.yml](../.github/workflows/ci.yml)

### The settings that matter more than the YAML dialect

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```
A new push makes the in-flight run obsolete. Cancelling saves runner minutes and
stops stale red X's from confusing reviewers.

```yaml
strategy:
  fail-fast: false
  matrix: { browser: [chromium, firefox, webkit] }
```
Without `fail-fast: false`, chromium failing cancels firefox and webkit — and
you lose the information that would have told you it was a cross-browser issue.

```yaml
timeout-minutes: 25
```
On every job. A hung browser otherwise burns six hours of runner time.

---

## Speed

| Lever | Typical gain |
|---|---|
| `-n auto` (xdist) | 3–5× |
| Cache Playwright browsers | 60–90 s/job |
| Cache pip | 20–40 s/job |
| Run services before web | Fails fast on ~70% of real breaks |
| Seed via API instead of UI | 2–10× on affected tests |
| Shard by layer, not by file | Better balance |

In this repo: 65 s sequential → 40 s with `-n 4`. On a 16-core CI runner the
services layer alone drops under 10 s.

**Measure before optimising.** `--durations=10` is already in `addopts`. Nine
times out of ten a suite is slow because of setup, not because of the tests.

---

## Reporting: three audiences, three artifacts

| Audience | Wants | Artifact |
|---|---|---|
| The engineer who broke it | Why, in 30 seconds | Allure with screenshot, DOM, request/response, trace |
| The reviewer | Did anything break? | JUnit XML → PR check annotations |
| The team lead | Are we getting better? | Allure history: trends, flaky detection, durations |

### Allure

```bash
pytest --alluredir=allure-results
allure serve allure-results
```

Integrated in [framework/utils/reporting.py](../framework/utils/reporting.py)
behind a graceful-degradation shim, so the framework never hard-depends on it.

**Steps** turn "test_checkout failed" into "test_checkout failed at *Place
order*":

```python
with step(f"Add product {product_id} x{quantity} to cart"):
    ...
```

**Attachments** are added automatically: every HTTP request/response (redacted),
and on failure a screenshot, the DOM, the browser console and — on mobile — the
page source and logcat.

**Environment metadata** is written by `pytest_configure`:

```
Environment=local
Web.BaseUrl=http://127.0.0.1:8000
Browser=chromium
Python=3.14.7
```

Six months from now, "which build was this?" is the first question anyone asks
about a red run. Answer it in the artifact.

### History is the step everyone skips

```yaml
- uses: actions/checkout@v4
  with: { ref: gh-pages, path: gh-pages }
- run: cp -r gh-pages/last-history all-results/history || true
```

Without history, every report is an isolated snapshot. With it you get **trends,
flaky-test detection, and duration drift** — the three things that let you manage
a suite rather than just run it. It is four lines of YAML and it is the
difference between a report and a dashboard.

---

## The gate: what should block a merge

| Result | Blocks merge? |
|---|---|
| `smoke` failure | **Yes**, always |
| `regression` failure | Yes |
| Known `xfail` | No — that's the point |
| Test marked `flaky` | No — quarantined, but visible |
| a11y `serious`/`critical` | Yes |
| a11y `moderate`/`minor` | No — report only |
| New visual diff | No — requires human review |

Two principles:

1. **A gate people can't fix today gets disabled within a week.** Ratchet
   thresholds down over time instead of starting at maximum strictness.
2. **Never gate on a metric you can game.** Coverage percentage is the classic
   example — see [Module 9](09-strategy.md).

---

## Quarantine, done properly

```python
@pytest.mark.flaky
@pytest.mark.xfail(reason="FLAKE-231: race in the cart badge", strict=False)
def test_something(): ...
```

Rules that make quarantine a tool rather than a graveyard:

- **A ticket number is mandatory.** No ticket, no quarantine.
- **Quarantined tests still run** — in a non-blocking job. A quarantined test
  that stops running is a deleted test with extra steps.
- **Two-week expiry.** Fixed or deleted. Review the list every sprint.
- **A cap.** If more than ~2% of the suite is quarantined, stop feature work and
  fix the suite. Past that point nobody trusts any result.

### `--reruns` is a measurement tool, not a fix

```bash
pytest --reruns 1 --reruns-delay 2
```

Legitimate use: keeping CI usable *while* you fix the root cause, and
identifying which tests are flaky (a test that passes on rerun is flaky by
definition — log it). Illegitimate use: leaving it on forever, at which point
you have automated the act of ignoring bugs. Note that `--reruns` is in the CI
job in this repo, not in `addopts` — that placement is deliberate.

---

## Docker: reproducibility

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble
```

Start from Playwright's image — it ships the exact browser builds and the system
libraries and **fonts** they need. Keep the tag pinned to the same version as the
`playwright` package; a driver/browser mismatch is a real failure mode.

"Works on my machine" in test automation is almost always one of three things: a
different browser build, a different font set, or a different timezone. The
container pins all three (`TZ=UTC` in
[docker-compose.yml](../docker-compose.yml)).

```yaml
depends_on:
  sut: { condition: service_healthy }
```

Depend on *healthy*, not on *started*. "Started" is a race.

---

## Notifications

Report to where people already are, and be brutal about signal:

- **Green build:** say nothing. A channel that pings on success is muted within
  a week, and then the failures are muted too.
- **Newly failing:** notify, with the test name, the failure message and a link.
- **Still failing:** don't re-notify every run. Once per state change.
- **Nightly:** a summary with the trend, not a wall of test names.

---

## Checkpoint

1. Why does the `web` job depend on `services`?
2. What does `fail-fast: false` protect you from in a browser matrix?
3. Why is `--reruns` in the CI job rather than in `addopts`?
4. What does Allure history give you that a single report cannot?
5. Name two rules that stop a quarantine list becoming a graveyard.

Next: [Module 8 — Flakiness](08-flakiness.md)
