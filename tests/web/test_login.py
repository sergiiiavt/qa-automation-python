"""Login through the UI.

This is the *one* place the suite logs in through the form. Every other web test
gets its session from `storage_state`. If login breaks, exactly these tests go
red and the diagnosis is immediate — instead of 200 tests failing at once and
burying the signal.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.data.factories import persona
from framework.web.pages import App, LoginPage


@pytest.mark.smoke
def test_user_can_log_in_with_valid_credentials(app: App) -> None:
    user = persona("standard")

    products = app.login.open().login(user.username, user.password)

    # `expect` retries until the timeout — no sleeps, no manual polling.
    expect(products.page).to_have_url(f"{products.base_url}/")
    expect(products.testid("logout")).to_be_visible()


@pytest.mark.parametrize(
    ("username", "password", "expected_error"),
    [
        ("alice", "nope", "Invalid credentials"),
        ("ghost", "wonderland", "Invalid credentials"),
        ("", "wonderland", "Username and password are required"),
        ("alice", "", "Username and password are required"),
        ("", "", "Username and password are required"),
    ],
)
def test_login_errors_are_shown_to_the_user(
    app: App, username: str, password: str, expected_error: str
) -> None:
    """Assert on the message the user reads, not on an internal state flag.
    A test that passes while the user sees a blank box is worse than no test."""
    login = app.login.open()

    login.login_expecting_failure(username, password)

    expect(login.error).to_have_text(expected_error)
    expect(login.page).to_have_url(f"{login.base_url}/login")


def test_error_message_is_announced_to_assistive_technology(app: App) -> None:
    """`role="alert"` is what makes a screen reader speak the error. Without it
    a blind user gets silence after pressing the button."""
    login = app.login.open()

    login.login_expecting_failure("alice", "nope")

    expect(login.page.get_by_role("alert")).to_contain_text("Invalid credentials")


def test_password_field_is_masked(app: App) -> None:
    login = app.login.open()

    expect(login.password).to_have_attribute("type", "password")
    expect(login.password).to_have_attribute("autocomplete", "current-password")


def test_login_form_is_keyboard_operable(app: App) -> None:
    """Tab order and Enter-to-submit. A surprising number of production forms
    fail this, and it costs one test to know."""
    user = persona("standard")
    login = app.login.open()

    login.username.click()
    login.page.keyboard.type(user.username)
    login.page.keyboard.press("Tab")
    login.page.keyboard.type(user.password)
    login.page.keyboard.press("Enter")

    expect(login.page).to_have_url(f"{login.base_url}/")


def test_session_persists_across_reload(app_as_user: App) -> None:
    products = app_as_user.products.open()

    products.reload()

    expect(products.testid("logout")).to_be_visible()


def test_logout_clears_the_session(app_as_user: App) -> None:
    products = app_as_user.products.open()

    products.open_nav()
    products.testid("logout").click()

    expect(products.page).to_have_url(f"{products.base_url}/login")
    # Reopening a protected page must not restore the session.
    LoginPage(products.page).page.goto(f"{products.base_url}/cart")
    expect(products.page).to_have_url(f"{products.base_url}/login")
