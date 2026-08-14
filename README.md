# Test Automation in Python — Web, Mobile, Services

A complete, runnable course **and** a production-shaped framework. Every example
in the docs executes against a demo application bundled in this repo, so nothing
here is pseudocode and nothing depends on a third-party demo site staying up.

```
170 tests · 3 layers · runs in 40s on 4 cores · zero external dependencies
```

## What you get

| | |
|---|---|
| **A framework** | Layered, typed, documented. `framework/` is library code you can lift into a real project. |
| **A system under test** | `sut/` — a FastAPI shop with a real OpenAPI schema and a responsive UI. API, web and mobile-web tests all target it. |
| **A real native app** | `apps/` — Sauce Labs' MIT-licensed "My Demo App" (Android), bundled so `tests/mobile` runs against something real, not placeholder locators. |
| **A course** | `docs/` — 11 modules from pytest fundamentals to CI, flakiness and strategy. |
| **Exercises** | `docs/10-exercises.md` — 30 graded tasks with solution criteria. |

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate    # Linux/macOS: source .venv/bin/activate
pip install -e .
playwright install chromium
pytest tests/services -q
```

The suite starts and stops the demo app itself — nothing to run first.

```bash
pytest tests -n auto          # everything, in parallel
pytest -m smoke               # the fast gate
pytest tests/web --headed     # watch the browser
uvicorn sut.app:app --reload  # explore the app: http://127.0.0.1:8000 (docs at /docs)
```

## Layout

```
framework/          The reusable library — no test logic lives here
├── config.py         Typed, layered settings (env vars > .env > YAML > defaults)
├── http/client.py    Instrumented httpx client: retries, logging, redaction
├── api/              Models + service objects (the API's "page objects")
├── web/              Playwright base page, page objects, components
├── mobile/           Appium driver factory, screen objects, gestures
├── data/factories.py Builders, factories, personas, uniqueness
└── utils/            Assertions, waits, reporting adapters

tests/
├── services/       92 API tests: CRUD, auth, boundaries, contract, property-based
├── web/            64 browser tests: flows, mobile-web emulation, a11y, visual
└── mobile/         14 Appium tests: native app + real-device mobile web

sut/                The demo application under test
apps/               A bundled, MIT-licensed real app for the native-mobile tests
docs/               The course
conftest.py         Root fixtures, hooks, CLI options
```

## The course

Work through it in order; each module builds on the last.

| # | Module | You will be able to |
|---|--------|---------------------|
| 0 | [Curriculum & how to study](docs/00-curriculum.md) | Plan a realistic 8-week path |
| 1 | [pytest foundations](docs/01-pytest-foundations.md) | Use fixtures, scopes, parametrize, markers, hooks properly |
| 2 | [Framework architecture](docs/02-architecture.md) | Design layers that don't rot after 300 tests |
| 3 | [Services / API testing](docs/03-services.md) | Build a typed API client, service objects, contract tests |
| 4 | [Web UI with Playwright](docs/04-web.md) | Write UI tests that don't flake |
| 5 | [Mobile: native + mobile web](docs/05-mobile.md) | Choose emulation vs. real devices; drive Appium 3 |
| 6 | [Test data](docs/06-test-data.md) | Make tests parallel-safe by construction |
| 7 | [CI & reporting](docs/07-ci-reporting.md) | Ship a pipeline people trust |
| 8 | [Flakiness](docs/08-flakiness.md) | Diagnose and eliminate the seven root causes |
| 9 | [Strategy & metrics](docs/09-strategy.md) | Decide what to automate, and prove the value |
| 10 | [Exercises](docs/10-exercises.md) | Practise, with acceptance criteria |
| — | [Cheat sheet](docs/cheatsheet.md) | Look things up fast |

## Real defects this suite found while it was being written

Not hypotheticals — these came out of actual runs, and the fixes are in the git
history. They are worked through in the docs because *finding* bugs is the skill,
not writing assertions.

| Found by | Defect |
|---|---|
| Schemathesis contract test | API returned undocumented `400`/`401` — the OpenAPI spec was lying |
| Schemathesis, second run | The "fix" declared `detail: string` while the service returns a list — a wrong contract is worse than a missing one |
| Mobile-web touch-target test | Hamburger button was 40×40 px, below the 44 px minimum |
| Dark-mode axe audit | White text on the light accent colour: 2.7:1 contrast, fails WCAG AA |
| `pytest -n 4` | Three cart tests passed alone and failed in parallel — all four workers shared one account |
| `pytest -n 4`, later | Intermittent `ConnectionRefusedError`: the demo app was owned by a session fixture, so whichever worker finished first killed the server the other three were still using |
| `pytest -n 4`, later still | Intermittent `FailedHealthCheck` from Hypothesis on the two parameterless operations — a finding about the *tooling*, not the product |
| BOLA test | Any user can read any other user's order (documented as `xfail`, ticket SHOP-114) |
| Cross-browser CI matrix | A Chromium-only launch flag made every WebKit test fail; invisible until three engines actually ran |
| Cross-browser CI matrix | A visual baseline recorded on Windows/Chromium failed on every engine on Linux CI — a screenshot is only comparable within one environment |
| Reviewing a sibling framework | This repo's own `browser_context_args` always recorded video and never deleted it — 222 files after one local run, contradicting the "failure-only artifacts" principle the docs teach. Fixed by using pytest-playwright's own `--video=retain-on-failure` instead of hand-rolling the policy |
| Same review | The native-mobile driver factory set `noReset=False` while its comment claimed the opposite — the comment was never checked against the code |
| First real local Windows setup, mobile | `.env.example` used flat keys (`QA_DEVICE_NAME`) for fields that live under nested settings groups; `Settings`' `extra="forbid"` turned every one of them into a startup `ValidationError` instead of a typo warning. Fixed the template and documented the `__` delimiter requirement in `framework/config.py` |
| Same setup | `MobileSettings.app_path`'s `_absolutize` validator never ran on the field's own default — a Pydantic v2 gotcha (`validate_default` defaults off) — so the bundled apk path resolved relative to wherever the Appium *server* process happened to be launched from, not the repo. Fixed with `Field(..., validate_default=True)` |
| Same setup | `BaseScreen.text_of()` unconditionally queried the `value` attribute; this Appium/UiAutomator2 version raises for it on Android instead of returning `None` as older tooling did. Never exercised successfully on Android before — the login-error assertions that call it had never gotten this far in a real run |
| Same setup | `noReset=True` (intentional, for install speed) means a new session resumes the app exactly where the last one left it — a test starting mid-checkout instead of at the Catalog landing screen. Fixed by explicitly terminating the app in the `driver` fixture's teardown, not on next launch |
| Same setup | Appium's default `appWaitDuration` (~20s) killed roughly 1 in 3 cold app launches on a dev machine also running Android Studio, the emulator and an IDE — not broken, just slower than the default assumes. Bumped to 60s, same rationale as the existing `uiautomator2ServerLaunchTimeout` |
| Same setup | `platform_version` was pinned to `"14"` in *two* places (`MobileSettings`' default and `config/local.yaml`) as an exact-match Appium capability, not a hint — it hard-fails device lookup the moment a dev's AVD is on a different OS image, which is exactly what Android Studio's own "recommended" system image will eventually be. Made it optional in both places; Appium falls back to whatever's connected |

## The full mobile pipeline

The nightly `mobile` CI job doesn't just install the apk committed at
`apps/`. A `build-mobile-app` job compiles that same app fresh from its
upstream source (pinned to the exact commit that produced the bundled
binary) and the `mobile` job installs and tests *that* build instead — a
real build → deploy → test → gate chain, not just a test job. See
["The full pipeline"](docs/05-mobile.md#the-full-pipeline-a-real-build-stage-not-just-a-bundled-binary)
in Module 5.

## Requirements

- Python 3.11+ (developed on 3.14)
- Node 20+, Appium 3 + the UiAutomator2 driver, and an Android emulator or
  device — only for `tests/mobile`. The app itself (`apps/mda-2.2.0-25.apk`)
  is already bundled; nothing to download.
- Docker — optional, for reproducible runs (`docker compose up tests`)

## Licence

Use it, fork it, teach from it.
