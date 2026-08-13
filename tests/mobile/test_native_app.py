"""Native app tests (Appium), against the bundled Sauce Labs "My Demo App".

These skip automatically unless an Appium server is reachable — see the root
conftest. See [apps/README.md](../../apps/README.md) for what the app is and
[framework/mobile/screens.py](../../framework/mobile/screens.py) for which
screens have verified locators. To target your own app instead, point
`QA_APP_PATH` at it and replace the screen objects — the fixtures and test
shapes below transfer; the locators do not.

What is worth automating on a real device, in priority order:

  1. Things that only exist on device: permissions dialogs, biometrics, push,
     deep links, background/foreground, network loss, rotation, back button.
  2. The one or two critical revenue journeys.
  3. Platform-specific UI you cannot emulate.

What is NOT worth automating on device: business-rule permutations, validation
tables, error messages. Push those to the services layer — they run in
milliseconds there and take minutes here. (This app has no service layer of
its own to push them to, which is exactly why its own validation checks below
are kept to the two the login form actually has — not padded out with more.)
"""

from __future__ import annotations

import pytest

from framework.mobile.screens import (
    LOCKED_OUT_USERNAME,
    VALID_PASSWORD,
    VALID_USERNAME,
    CatalogScreen,
    LoginScreen,
)

pytestmark = pytest.mark.mobile_native


@pytest.mark.smoke
def test_user_can_log_in(login_screen: LoginScreen) -> None:
    catalog = login_screen.login(VALID_USERNAME, VALID_PASSWORD)

    assert catalog.is_displayed(CatalogScreen.root), "Catalog did not reappear after login"


def test_login_requires_a_username(login_screen: LoginScreen) -> None:
    login_screen.login_expecting_failure("", VALID_PASSWORD)

    assert login_screen.username_error, "No validation error shown for a blank username"


def test_login_requires_a_password(login_screen: LoginScreen) -> None:
    login_screen.login_expecting_failure(VALID_USERNAME, "")

    assert login_screen.password_error, "No validation error shown for a blank password"


@pytest.mark.smoke
def test_locked_out_user_is_rejected(login_screen: LoginScreen) -> None:
    """The app's one *business-rule* validation, not just a required-field
    check — worth the device time because it is specific to this account's
    server-side state, not something a unit test could stand in for."""
    login_screen.login_expecting_failure(LOCKED_OUT_USERNAME, VALID_PASSWORD)

    assert "locked out" in login_screen.password_error.lower()


def test_app_survives_backgrounding(logged_in_catalog_screen: CatalogScreen) -> None:
    """Backgrounding is where mobile apps lose state, drop sockets and crash.
    This is a device-only scenario and one of the highest-value mobile tests —
    nothing at the API or emulated-web layer can produce it."""
    logged_in_catalog_screen.driver.background_app(5)

    assert logged_in_catalog_screen.is_displayed(CatalogScreen.root), (
        "Catalog did not survive being backgrounded and foregrounded"
    )


def test_rotation_does_not_lose_the_session(logged_in_catalog_screen: CatalogScreen) -> None:
    """On Android, rotation destroys and recreates the Activity. Anything not
    saved in onSaveInstanceState is gone — a defect class unique to mobile."""
    driver = logged_in_catalog_screen.driver
    driver.orientation = "LANDSCAPE"
    try:
        assert logged_in_catalog_screen.is_displayed(CatalogScreen.root), (
            "Rotation lost the logged-in session"
        )
    finally:
        driver.orientation = "PORTRAIT"


def test_back_navigation_returns_to_the_catalog(catalog_screen: CatalogScreen) -> None:
    """Android's hardware back button has no web equivalent and is a reliable
    source of broken navigation stacks."""
    login = catalog_screen.open_menu().open_login()
    assert login.is_displayed(LoginScreen.root)

    login.driver.back()

    assert catalog_screen.is_displayed(CatalogScreen.root), "Back did not return to the catalog"


@pytest.mark.slow
def test_app_handles_loss_of_connectivity(catalog_screen: CatalogScreen) -> None:
    """Airplane-mode simulation. `set_network_connection` is Android-only; the
    skip is explicit rather than a silent pass."""
    if not catalog_screen.is_android:
        pytest.skip("Network condition control is Android-only via UiAutomator2")

    driver = catalog_screen.driver
    driver.set_network_connection(1)  # 1 = airplane mode
    try:
        assert catalog_screen.is_displayed(CatalogScreen.root, timeout=5), (
            "App crashed or showed a blank screen when offline"
        )
    finally:
        driver.set_network_connection(6)  # 6 = wifi + data
