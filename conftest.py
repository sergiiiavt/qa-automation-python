"""Root conftest — shared by every layer.

Conftest layering is the framework's skeleton:

    conftest.py               <- SUT lifecycle, settings, CLI options, hooks
    tests/services/conftest.py <- ApiClient + ShopApi fixtures
    tests/web/conftest.py      <- Playwright context/page tuning, Page Objects
    tests/mobile/conftest.py   <- Appium driver, Screen Objects

Nothing in a lower layer imports from a sibling layer. A web test must never
need an Appium import to collect — that is what makes `pytest tests/services`
run in two seconds on a machine with no browsers installed.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pytest

from framework.config import settings
from framework.http.client import wait_for_service
from framework.utils.reporting import attach_text

ROOT = Path(__file__).parent
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)


# ---------------------------------------------------------------------------
# CLI options — anything a human might want to flip at run time.
# ---------------------------------------------------------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("qa-framework")
    group.addoption("--env", default=None, help="Target environment: local|dev|stage")
    group.addoption(
        "--no-sut",
        action="store_true",
        help="Do not start the bundled demo app; test whatever --base-url points at.",
    )
    group.addoption(
        "--platform",
        default=None,
        choices=["android", "ios"],
        help="Mobile platform for tests/mobile.",
    )
    group.addoption(
        "--real-device-web",
        action="store_true",
        help="Run mobile-web tests through Appium on a device instead of emulating in Playwright.",
    )


#: Where the controller keeps the demo-app process it owns. A stash key rather
#: than a module global, so the value cannot leak between runs in the same process.
SUT_PROCESS: pytest.StashKey[tuple[subprocess.Popen, IO[str]]] = pytest.StashKey()


def pytest_configure(config: pytest.Config) -> None:
    if env := config.getoption("--env"):
        os.environ["QA_ENV"] = env
    if platform := config.getoption("--platform"):
        os.environ["QA_PLATFORM"] = platform
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Only the controller owns the shared demo app. See `_start_sut` for the
    # xdist lifecycle bug that made this necessary.
    if not _is_xdist_worker(config):
        _start_sut(config)

    # Stamp environment metadata into the Allure report. Six months from now,
    # "which build was this?" is the first question anyone asks about a red run.
    allure_dir = config.getoption("--alluredir", default=None)
    if allure_dir:
        env_file = Path(allure_dir)
        env_file.mkdir(parents=True, exist_ok=True)
        (env_file / "environment.properties").write_text(
            "\n".join(
                [
                    f"Environment={settings.env}",
                    f"API.BaseUrl={settings.api.base_url}",
                    f"Web.BaseUrl={settings.web.base_url}",
                    f"Browser={settings.web.browser}",
                    f"Mobile.Platform={settings.mobile.platform}",
                    f"Python={sys.version.split()[0]}",
                    f"CI={os.getenv('CI', 'false')}",
                ]
            ),
            encoding="utf-8",
        )


def pytest_unconfigure(config: pytest.Config) -> None:
    """Runs after every xdist worker has finished — the only safe moment to stop
    a server they all share."""
    _stop_sut(config)


# ---------------------------------------------------------------------------
# System under test lifecycle
# ---------------------------------------------------------------------------
def _port_open(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _sut_endpoint() -> tuple[str, str, int]:
    base_url = settings.api.base_url
    host, _, port_str = base_url.removeprefix("http://").removeprefix("https://").partition(":")
    return base_url, host, int(port_str or 80)


def _is_xdist_worker(config: pytest.Config) -> bool:
    """True inside a `-n` worker subprocess, False in the controller (and in a
    plain single-process run, which is its own controller)."""
    return hasattr(config, "workerinput")


def _start_sut(config: pytest.Config) -> None:
    """Start the demo app, owned by the process that owns the whole run.

    ### Why this is a hook and not a fixture

    It *was* a session-scoped autouse fixture. That is wrong under xdist, and
    the bug it caused is worth keeping in mind: "session" means **once per
    worker**, so with `-n 4` one worker won the race to bind the port, started
    uvicorn as its child, and then — the moment *its* last test finished —
    its fixture teardown killed the server while the other three workers were
    still running. The symptom was an intermittent `ConnectionRefusedError` in
    whichever tests happened to be in flight, which looks like a network blip
    and is actually a lifecycle bug.

    `pytest_configure` / `pytest_unconfigure` run in the **controller** process,
    before any worker starts and after every worker has finished. That is the
    only place a resource shared by all workers can correctly live.
    """
    base_url, host, port = _sut_endpoint()

    if config.getoption("--no-sut") or _port_open(host, port):
        wait_for_service(f"{base_url}/api/health")
        return

    # Log to a file rather than a PIPE: an unread pipe fills its buffer and
    # deadlocks the child, and leaving it unclosed leaks a file descriptor that
    # surfaces as a ResourceWarning at teardown.
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    log_file = (settings.artifacts_dir / "sut.log").open("w", encoding="utf-8")
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "sut.app:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    config.stash[SUT_PROCESS] = (process, log_file)
    wait_for_service(f"{base_url}/api/health", timeout=40)


def _stop_sut(config: pytest.Config) -> None:
    owned = config.stash.get(SUT_PROCESS, None)
    if owned is None:
        return
    process, log_file = owned
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    log_file.close()


@pytest.fixture(scope="session", autouse=True)
def sut() -> str:
    """The base URL of a demo app that is already running.

    Workers never start or stop it — they only confirm it is reachable. Keeping
    the fixture autouse means a missing server fails loudly at setup rather than
    as a confusing connection error in the middle of an assertion.
    """
    base_url, _, _ = _sut_endpoint()
    wait_for_service(f"{base_url}/api/health", timeout=40)
    return base_url


@pytest.fixture(scope="session")
def base_url(sut: str) -> str:
    return sut


@pytest.fixture(scope="session")
def worker_account(base_url: str, worker_id: str) -> tuple[str, str]:
    """A dedicated user account for this xdist worker.

    ### Why this fixture exists

    The first parallel run of this suite (`pytest -n 4`) failed three cart tests
    that all passed sequentially. Cause: every worker logged in as the same
    `alice` and mutated the same server-side cart. Classic, and the reason
    "works locally, flaky on CI" is such a common complaint.

    Three ways to fix a collision like this, in order of preference:

      1. **Isolate the data** — one account per worker (this fixture). Keeps full
         parallelism. Needs the backend to support self-service creation.
      2. **Isolate the state** — a per-test tenant/namespace, if the product has one.
      3. **Serialise** — `pytest-xdist --dist loadgroup` with an `xdist_group`
         marker. Correct but slow; a last resort, not a first response.

    Never "fix" it by adding a sleep or a retry. The data was wrong, not late.
    """
    import httpx

    username = f"qa_{worker_id}_{uuid.uuid4().hex[:8]}"
    password = "Str0ng!Passw0rd"
    response = httpx.post(
        f"{base_url}/api/auth/register",
        json={"username": username, "password": password},
        timeout=10,
    )
    assert response.status_code == 201, f"Could not provision a worker account: {response.text}"
    return username, password


# ---------------------------------------------------------------------------
# Hooks: failure diagnostics and reporting
# ---------------------------------------------------------------------------
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Publish each phase's result onto the item.

    This is the standard trick that lets a *fixture teardown* know whether the
    test passed: `if request.node.rep_call.failed: capture_screenshot()`.
    Without it, a fixture cannot distinguish a clean exit from a failure.
    """
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


@pytest.fixture(autouse=True)
def _test_context(request: pytest.FixtureRequest) -> Iterator[None]:
    """Log boundaries and attach timing. Cheap, and invaluable in parallel runs
    where interleaved logs are otherwise unreadable."""
    started = time.monotonic()
    logging.getLogger("test").info("START %s", request.node.nodeid)
    yield
    duration = time.monotonic() - started
    logging.getLogger("test").info("END   %s (%.2fs)", request.node.nodeid, duration)
    if duration > 30:
        attach_text("slow-test", f"{request.node.nodeid} took {duration:.1f}s")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-mark by directory, and skip layers whose dependencies aren't present.

    Auto-marking beats hand-written `@pytest.mark.web` on 300 tests: markers stay
    correct by construction, and nobody forgets one.
    """
    for item in items:
        path = str(item.path)
        if f"{os.sep}services{os.sep}" in path:
            item.add_marker(pytest.mark.services)
        elif f"{os.sep}mobile{os.sep}" in path:
            item.add_marker(pytest.mark.mobile_native)
        elif f"{os.sep}web{os.sep}" in path:
            item.add_marker(pytest.mark.web)

    # Mobile tests need a live Appium server; skip rather than error when absent.
    if any(item.get_closest_marker("mobile_native") for item in items):
        appium = settings.mobile.appium_url.removeprefix("http://")
        host, _, port = appium.partition(":")
        if not _port_open(host, int(port or 4723)):
            skip = pytest.mark.skip(reason=f"No Appium server at {settings.mobile.appium_url}")
            for item in items:
                if item.get_closest_marker("mobile_native"):
                    item.add_marker(skip)


def pytest_report_header(config: pytest.Config) -> list[str]:
    return [
        f"env: {settings.env} | api: {settings.api.base_url} | web: {settings.web.base_url}",
        f"browser: {settings.web.browser} (headless={settings.web.headless}) | "
        f"mobile: {settings.mobile.platform}/{settings.mobile.device_name}",
    ]
