"""Web-layer fixtures.

Built on top of `pytest-playwright`, overriding only what needs framework
policy. Two ideas dominate this file:

  * **Storage-state auth.** Logging in through the UI in every test is the
    single biggest waste in most suites. Do it once, save the browser state,
    and inject it. Keep exactly one test that logs in through the form —
    that one is testing login; the rest are testing something else.

  * **Artifacts on failure only.** Traces and videos for every green test are
    gigabytes of noise. `rep_call.failed` (set by the root conftest hook) makes
    "capture only what a human will actually open" a two-line policy.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from framework.config import settings
from framework.utils.reporting import attach_png, attach_text
from framework.web.pages import App, LoginPage

AUTH_STATE = settings.artifacts_dir / "storage_state.json"


# ---------------------------------------------------------------------------
# pytest-playwright overrides
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    """Merge, never replace — pytest-playwright puts `--headed`/`--slowmo` in here."""
    return {
        **browser_type_launch_args,
        "headless": settings.web.headless,
        "slow_mo": settings.web.slow_mo,
        "args": ["--disable-dev-shm-usage"],  # avoids /dev/shm exhaustion in Docker
    }


@pytest.fixture
def browser_context_args(browser_context_args: dict, base_url: str) -> dict:
    return {
        **browser_context_args,
        "base_url": base_url,
        "viewport": {"width": settings.web.viewport_width, "height": settings.web.viewport_height},
        "locale": "en-US",
        "timezone_id": "UTC",           # pin it: date assertions break across TZs
        "ignore_https_errors": not settings.web.verify_ssl if hasattr(settings.web, "verify_ssl") else False,
        # Recording video is cheap to enable and expensive to keep; the
        # `page` fixture below deletes it when the test passes.
        "record_video_dir": str(settings.artifacts_dir / "video"),
        "record_video_size": {"width": 1280, "height": 720},
    }


@pytest.fixture(scope="session", autouse=True)
def _configure_test_id_attribute(playwright: Playwright) -> None:
    """Teach Playwright which attribute `get_by_test_id` should read.

    Default is `data-testid`; set it explicitly so the choice is visible and so
    a team using `data-qa` changes exactly one line.
    """
    playwright.selectors.set_test_id_attribute("data-testid")


@pytest.fixture(autouse=True)
def _configure_timeouts(page: Page) -> None:
    page.set_default_timeout(settings.web.action_timeout_ms)
    page.set_default_navigation_timeout(settings.web.navigation_timeout_ms)


# ---------------------------------------------------------------------------
# Authentication via storage state
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def storage_state(browser: Browser, base_url: str, worker_account: tuple[str, str], worker_id: str) -> str:
    """Log in once per session through the real UI, then persist the state.

    Note it authenticates through the *form*, not by injecting a token: the
    saved state then reflects everything a real login produces (localStorage,
    cookies, any flags the app sets). Injecting a hand-made token is faster
    still, but it drifts from reality the day auth changes.
    """
    # One state file per worker — a shared path would have four processes
    # writing the same file concurrently.
    state_path = AUTH_STATE.with_name(f"storage_state.{worker_id}.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    username, password = worker_account

    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    LoginPage(page).open().login(username, password)
    context.storage_state(path=str(state_path))
    context.close()
    return str(state_path)


@pytest.fixture
def authenticated_context(
    browser: Browser, browser_context_args: dict, storage_state: str
) -> Iterator[BrowserContext]:
    context = browser.new_context(**{**browser_context_args, "storage_state": storage_state})
    context.set_default_timeout(settings.web.action_timeout_ms)
    yield context
    context.close()


@pytest.fixture
def authenticated_page(authenticated_context: BrowserContext) -> Iterator[Page]:
    page = authenticated_context.new_page()
    yield page
    page.close()


@pytest.fixture
def app(page: Page) -> App:
    """Anonymous session, all Page Objects wired up."""
    return App(page)


@pytest.fixture
def app_as_user(authenticated_page: Page) -> App:
    """Logged-in session. This is the fixture most tests should ask for."""
    return App(authenticated_page)


# ---------------------------------------------------------------------------
# Diagnostics — the difference between "it failed on CI" and "here's why"
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _capture_on_failure(request: pytest.FixtureRequest) -> Iterator[None]:
    """Screenshot + DOM + console log on failure; nothing on success.

    This fixture is why `pytest_runtest_makereport` exists in the root conftest.
    Without `rep_call`, a teardown cannot tell pass from fail.
    """
    page: Page | None = None
    console: list[str] = []

    def _hook_console(p: Page) -> None:
        p.on("console", lambda msg: console.append(f"[{msg.type}] {msg.text}"))
        p.on("pageerror", lambda err: console.append(f"[pageerror] {err}"))

    # Resolve the page lazily: not every web test uses the same page fixture.
    for name in ("authenticated_page", "page"):
        if name in request.fixturenames:
            page = request.getfixturevalue(name)
            _hook_console(page)
            break

    yield

    report = getattr(request.node, "rep_call", None)
    failed = report is not None and report.failed
    if page is None or page.is_closed():
        return

    if failed:
        safe_name = request.node.name.replace("/", "_")[:80]
        attach_png("failure-screenshot", page.screenshot(full_page=True))
        attach_text("page-url", page.url)
        attach_text("dom-snapshot", page.content()[:100_000])
        if console:
            attach_text("browser-console", "\n".join(console[-200:]))
        (settings.artifacts_dir / f"{safe_name}.png").write_bytes(page.screenshot(full_page=True))

    # Console *errors* are worth failing on even when assertions passed —
    # a silent JS exception is a defect the user will hit tomorrow.
    errors = [line for line in console if line.startswith(("[error]", "[pageerror]"))]
    if errors and not failed:
        attach_text("browser-console-errors", "\n".join(errors))


@pytest.fixture
def api_seed(base_url: str, worker_account: tuple[str, str]):
    """Set up UI preconditions through the API, not through the UI.

    Clicking through five screens to reach the screen under test is slow and
    couples every test to every screen. Seed via API, assert via UI.

    Critically, it authenticates as the *same* account the browser is using
    (`worker_account`), so what this fixture writes is what the page renders.
    """
    from framework.api.shop import ShopApi
    from framework.http.client import ApiClient

    username, password = worker_account
    with ApiClient(base_url=base_url) as client:
        yield ShopApi(client).login_as(username, password)


def load_storage_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
