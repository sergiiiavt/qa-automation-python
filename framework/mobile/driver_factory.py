"""Appium driver construction.

Targets Appium **3.x** with Appium-Python-Client **6.x**. Two things changed vs.
the tutorials you'll find from the Appium 1.x era:

  * `DesiredCapabilities` dicts are gone. Use the typed `*Options` objects
    (`UiAutomator2Options`, `XCUITestOptions`). They serialise to W3C caps and
    catch typos at construction instead of at session start.
  * Vendor-specific/security-gated capabilities need a namespace prefix
    (`appium:` for non-standard caps; `uiautomator2:adb_shell` style prefixes for
    server security features, which are **mandatory** in Appium 3).

Three session shapes are supported, because "mobile testing" means three
different things and conflating them is a common architecture mistake:

  1. NATIVE   — an installed .apk/.ipa. Uses accessibility ids / UiSelector.
  2. MOBILE WEB (real) — Chrome on Android or Safari on iOS, driven by Appium.
     Same web Page Objects, real device rendering, real mobile browser quirks.
  3. MOBILE WEB (emulated) — Playwright device descriptors. Not a real device,
     but 100x cheaper and catches the majority of responsive-layout defects.
     Lives in the web layer; see tests/web/test_mobile_web.py.
"""

from __future__ import annotations

import logging
from typing import Any

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.webdriver import WebDriver

from framework.config import Platform, settings

log = logging.getLogger("framework.mobile")


def _android_options(*, browser: str | None, app: str | None) -> UiAutomator2Options:
    m = settings.mobile
    opts = UiAutomator2Options()
    opts.platform_name = "Android"
    opts.device_name = m.device_name
    opts.platform_version = m.platform_version
    opts.automation_name = "UiAutomator2"
    opts.new_command_timeout = m.new_command_timeout

    if browser:
        # Mobile-web session: no app, Appium drives Chrome via chromedriver.
        opts.set_capability("browserName", "Chrome")
        # Let Appium fetch a matching chromedriver instead of pinning one by hand.
        opts.set_capability("appium:chromedriverAutodownload", True)
    elif app:
        opts.app = app
        # noReset=True skips wiping app data (and fullReset=True would also
        # uninstall it) between sessions, so Appium reuses the existing install
        # instead of a full reinstall each test. The previous version of this
        # factory set noReset=False — Appium's *default* — while the comment
        # claimed it skipped the reset; it did not. That mismatch was caught by
        # comparing against a working reference config, not by reading this
        # code in isolation, which is itself worth remembering: a comment that
        # describes what code *should* do is not evidence that it does.
        opts.set_capability("appium:noReset", True)
        opts.set_capability("appium:fullReset", False)
    else:
        raise ValueError("Provide either mobile.app_path or mobile.mobile_browser")

    # Stability caps that pay for themselves on CI.
    opts.set_capability("appium:autoGrantPermissions", True)
    opts.set_capability("appium:disableWindowAnimation", True)
    opts.set_capability("appium:ignoreHiddenApiPolicyError", True)
    opts.set_capability("appium:uiautomator2ServerLaunchTimeout", 60_000)
    return opts


def _ios_options(*, browser: str | None, app: str | None) -> XCUITestOptions:
    m = settings.mobile
    opts = XCUITestOptions()
    opts.platform_name = "iOS"
    opts.device_name = m.device_name
    opts.platform_version = m.platform_version
    opts.automation_name = "XCUITest"
    opts.new_command_timeout = m.new_command_timeout

    if browser:
        opts.set_capability("browserName", "Safari")
    elif app:
        opts.app = app
    else:
        raise ValueError("Provide either mobile.app_path or mobile.mobile_browser")

    opts.set_capability("appium:wdaLaunchTimeout", 120_000)
    opts.set_capability("appium:shouldTerminateApp", True)
    return opts


def _cloud_options(base: UiAutomator2Options | XCUITestOptions, build: str) -> Any:
    """Attach real-device-cloud vendor options when credentials are configured.

    Kept in the factory so a test never knows whether it runs on a local emulator
    or on a device farm. That indifference is the whole point of a driver factory.
    """
    m = settings.mobile
    if not (m.cloud_user and m.cloud_key):
        return base
    base.set_capability(
        "bstack:options",
        {
            "userName": m.cloud_user,
            "accessKey": m.cloud_key,
            "projectName": "QA Automation Course",
            "buildName": build,
            "sessionName": build,
            "debug": True,
            "networkLogs": True,
        },
    )
    return base


def create_driver(
    *,
    platform: Platform | None = None,
    browser: str | None = None,
    app: str | None = None,
    build: str = "local",
) -> WebDriver:
    """Build a session. Explicit args win over settings, so a single test can
    ask for a browser session inside an otherwise native-app run."""
    m = settings.mobile
    platform = platform or m.platform
    browser = browser if browser is not None else m.mobile_browser
    app = app if app is not None else m.app_path

    builder = _android_options if platform is Platform.ANDROID else _ios_options
    options = builder(browser=browser, app=app)
    options = _cloud_options(options, build)

    log.info("Starting %s session on %s (%s)", platform, m.device_name, m.appium_url)
    driver = webdriver.Remote(command_executor=m.appium_url, options=options)
    # Implicit wait stays at 0. Mixing implicit and explicit waits produces
    # unpredictable timeouts — pick explicit and never look back.
    driver.implicitly_wait(0)
    return driver
