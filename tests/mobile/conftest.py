"""Mobile-layer fixtures (Appium).

Everything here is written so that a machine *without* Appium can still collect
and skip cleanly (see `pytest_collection_modifyitems` in the root conftest).
A framework that explodes at import time on a developer laptop is a framework
developers route around.

Session scope is deliberately avoided for the driver. A mobile session is the
least stable resource in the whole stack — an OS dialog, a crash, a lost adb
connection and every subsequent test in the session is poisoned. Function-scoped
drivers cost ~5-10s each and save entire red builds.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from framework.config import Platform, settings
from framework.utils.reporting import attach_png, attach_text


@pytest.fixture(scope="session")
def mobile_platform(request: pytest.FixtureRequest) -> Platform:
    return settings.mobile.platform


@pytest.fixture
def driver(request: pytest.FixtureRequest) -> Iterator:
    """One Appium session per test.

    Does not depend on `base_url`. An earlier version of this fixture took it
    as a parameter without ever using it in the body — a leftover from when a
    native test cross-checked totals against the FastAPI SUT. That coupling is
    gone now that the native tests are self-contained against the bundled
    apk, so the unused parameter was dead code, not a real dependency.

    It does *not* stop the SUT from starting when you run `tests/mobile` —
    `sut` in the root conftest is `autouse=True` for the whole session, on
    purpose, because the mobile-web tests in this same directory still need
    it. Untangling that so a pure native-only run skips the web server
    entirely is a real improvement and a reasonable exercise, but it touches
    session-wide fixture architecture rather than this file — out of scope
    for what changed here.

    Note the teardown order: capture diagnostics *before* quitting, because a
    quit session can no longer produce a screenshot or a page source — the most
    common reason mobile failures arrive with no evidence attached.
    """
    from framework.mobile.driver_factory import create_driver

    session = create_driver(build=f"{settings.env}-{request.node.name}")
    try:
        yield session
    finally:
        report = getattr(request.node, "rep_call", None)
        if report is not None and report.failed:
            try:
                attach_png("failure-screenshot", session.get_screenshot_as_png())
                attach_text("page-source", session.page_source[:200_000])
                attach_text("session-capabilities", str(session.capabilities))
                if settings.mobile.platform is Platform.ANDROID:
                    logs = session.get_log("logcat")[-300:]
                    attach_text("logcat", "\n".join(entry["message"] for entry in logs))
            except Exception as exc:  # noqa: BLE001 - diagnostics must never mask the failure
                attach_text("diagnostics-error", f"Could not capture diagnostics: {exc}")
        session.quit()


@pytest.fixture
def mobile_web_driver(request: pytest.FixtureRequest) -> Iterator:
    """A real mobile *browser* session (Chrome on Android / Safari on iOS)."""
    from framework.mobile.driver_factory import create_driver

    session = create_driver(
        browser=settings.mobile.mobile_browser or "chrome",
        app=None,
        build=f"{settings.env}-mobileweb",
    )
    try:
        yield session
    finally:
        report = getattr(request.node, "rep_call", None)
        if report is not None and report.failed:
            attach_png("failure-screenshot", session.get_screenshot_as_png())
        session.quit()


@pytest.fixture
def catalog_screen(driver):
    """The app's landing screen after launch — no login needed to reach it."""
    from framework.mobile.screens import CatalogScreen

    return CatalogScreen(driver).wait_until_loaded()


@pytest.fixture
def login_screen(catalog_screen):
    """The login screen, reached the only way the app allows: through the
    hamburger menu on the catalog screen. There is no direct deep link."""
    return catalog_screen.open_menu().open_login()


@pytest.fixture
def logged_in_catalog_screen(login_screen):
    """Logged-in starting point.

    On mobile, seeding session state is harder than on web (no storage_state),
    so this pays the login cost once per test. If your app supports a deep link
    or a debug launch argument that skips login, use it — it is worth asking the
    mobile team for one; it can cut a device suite's runtime in half.

    Uses the bundled app's own fixed demo account (see
    framework/mobile/screens.py) — a separate, unrelated identity system from
    this course's FastAPI SUT, which is why it is not `persona("standard")`.
    """
    from framework.mobile.screens import VALID_PASSWORD, VALID_USERNAME

    return login_screen.login(VALID_USERNAME, VALID_PASSWORD)
