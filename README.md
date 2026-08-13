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
├── services/       90 API tests: CRUD, auth, boundaries, contract, property-based
├── web/            60 browser tests: flows, mobile-web emulation, a11y, visual
└── mobile/         15 Appium tests: native app + real-device mobile web

sut/                The demo application under test
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
| BOLA test | Any user can read any other user's order (documented as `xfail`, ticket SHOP-114) |

## Requirements

- Python 3.11+ (developed on 3.14)
- Node 20+ and Appium 3 — only for `tests/mobile`
- Docker — optional, for reproducible runs (`docker compose up tests`)

## Licence

Use it, fork it, teach from it.
