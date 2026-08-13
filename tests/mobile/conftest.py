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
def driver(request: pytest.FixtureRequest, base_url: str) -> Iterator:
    """One Appium session per test.

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
def login_screen(driver):
    from framework.mobile.screens import LoginScreen

    return LoginScreen(driver).wait_until_loaded()


@pytest.fixture
def products_screen(driver):
    """Logged-in starting point.

    On mobile, seeding session state is harder than on web (no storage_state),
    so this pays the login cost once per test. If your app supports a deep link
    or a debug launch argument that skips login, use it — it is worth asking the
    mobile team for one; it can cut a device suite's runtime in half.
    """
    from framework.data.factories import persona
    from framework.mobile.screens import LoginScreen

    user = persona("standard")
    return LoginScreen(driver).wait_until_loaded().login(user.username, user.password)
