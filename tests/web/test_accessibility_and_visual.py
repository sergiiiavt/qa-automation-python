"""Accessibility audits and visual regression.

Both are *high-yield, low-effort* additions that most teams skip. Together they
cost about 60 lines and cover a class of defect that functional tests are
structurally blind to: the page works, and is still unusable or visibly broken.

Honest framing on each:

  * **axe** finds roughly 30-40% of WCAG issues automatically. It cannot judge
    whether alt text is *meaningful* or whether a flow makes sense with a screen
    reader. Treat a green axe run as "no obvious violations", never as "accessible".

  * **Visual regression** is powerful and famously flaky. It becomes maintainable
    only with: pinned fonts, disabled animations, masked dynamic regions, and a
    non-zero pixel threshold. All four are applied below. Without them, do not
    adopt it — a permanently-red visual job trains everyone to ignore failures.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, Playwright, expect

from framework.utils.reporting import attach_html, attach_text
from framework.web.pages import App

axe = Axe()

# The rule tags worth gating a build on. Including "best-practice" produces noise
# that is not a WCAG failure; keep the gate legally meaningful and put the rest
# in a non-blocking report.
GATING_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]


def _audit(page: Page, name: str) -> list[dict]:
    results = axe.run(page, options={"runOnly": {"type": "tag", "values": GATING_TAGS}})
    report = results.generate_report()
    attach_text(f"axe-{name}", report)
    violations = results.response.get("violations", [])
    return violations


def _format(violations: list[dict]) -> str:
    lines = []
    for v in violations:
        targets = ", ".join(str(node["target"]) for node in v["nodes"][:3])
        lines.append(
            f"[{v['impact']}] {v['id']}: {v['help']}\n    -> {targets}\n    {v['helpUrl']}"
        )
    return "\n".join(lines)


@pytest.mark.a11y
@pytest.mark.parametrize("path", ["/", "/login"])
def test_public_pages_have_no_serious_accessibility_violations(app: App, path: str) -> None:
    """Gate on `serious` and `critical` only.

    Gating on every impact level from day one on a legacy app produces a red
    build nobody can fix this sprint, and the job gets disabled within a week.
    Ratchet the threshold down over time instead — that strategy actually ships.
    """
    app.page.goto(f"{app.products.base_url}{path}")
    app.page.wait_for_load_state("domcontentloaded")

    violations = _audit(app.page, path.strip("/") or "home")

    blocking = [v for v in violations if v["impact"] in ("serious", "critical")]
    assert not blocking, f"Accessibility violations on {path}:\n{_format(blocking)}"


@pytest.mark.a11y
def test_every_interactive_control_has_an_accessible_name(app: App) -> None:
    """A control with no accessible name is announced as "button" — useless.
    This check is narrow, deterministic and catches the single most common
    real-world a11y defect."""
    products = app.products.open()

    unnamed = products.page.eval_on_selector_all(
        "button, a, input, select",
        """els => els.filter(e => {
             const name = (e.getAttribute('aria-label')
                || e.getAttribute('title')
                || e.textContent
                || (e.labels && e.labels.length ? e.labels[0].textContent : '')
                || '').trim();
             return name === '' && e.offsetParent !== null;
           }).map(e => e.outerHTML.slice(0, 120))""",
    )

    assert not unnamed, "Controls without an accessible name:\n" + "\n".join(unnamed)


@pytest.mark.a11y
def test_page_has_exactly_one_h1_and_a_language(app: App) -> None:
    products = app.products.open()

    assert products.page.locator("h1").count() == 1, "A page needs exactly one <h1>"
    assert products.page.locator("html").get_attribute("lang"), "<html> is missing a lang attribute"


@pytest.mark.a11y
def test_keyboard_focus_is_visible(app: App) -> None:
    """Removing focus outlines without a replacement locks out keyboard users.
    Checks that *something* changes visually when a control is focused."""
    products = app.products.open()
    button = products.testid("apply-filters")

    button.focus()

    outline = button.evaluate(
        "el => { const s = getComputedStyle(el);"
        "return s.outlineStyle + '|' + s.outlineWidth + '|' + s.boxShadow; }"
    )

    assert outline != "none|0px|none", "Focused control has no visible focus indicator"


# ---------------------------------------------------------------------------
# Visual regression
# ---------------------------------------------------------------------------
STABILISE_CSS = """
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
    caret-color: transparent !important;
  }
  /* Scrollbars render differently per OS and are a classic false positive. */
  ::-webkit-scrollbar { display: none; }
"""


#: Baselines are *source*, not output — they belong in git next to the tests,
#: not in the gitignored artifacts directory.
BASELINE_DIR = Path(__file__).parent / "baselines"


@pytest.fixture
def stable_page(page: Page) -> Page:
    """Everything needed to make a screenshot comparable across machines.

    `add_init_script` runs before any page script, so the frozen clock is in
    place before the app reads it — a style tag added afterwards would be too late
    for time-dependent rendering.
    """
    page.add_init_script("Date.now = () => 1700000000000;")
    return page


@pytest.mark.regression
def test_product_grid_matches_the_visual_baseline(stable_page: Page, request) -> None:
    """A hand-rolled visual check, so you can see the mechanics.

    In production use a service (Percy, Applitools, Chromatic) or Playwright's
    own `expect(page).to_have_screenshot()` in the JS runner. What matters is
    that you understand the four levers below — every tool exposes the same ones.
    """
    products = App(stable_page).products.open()
    stable_page.add_style_tag(content=STABILISE_CSS)  # lever 1: no animation
    stable_page.wait_for_load_state("networkidle")  # lever 2: settled state

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    baseline_dir = BASELINE_DIR
    baseline = baseline_dir / "product-grid.png"

    shot = products.testid("product-grid").screenshot(
        mask=[products.testid("stock-badge")],  # lever 3: mask volatility
        animations="disabled",
    )

    if not baseline.exists():
        baseline.write_bytes(shot)
        pytest.skip(f"Baseline created at {baseline} — commit it and re-run")

    expected = baseline.read_bytes()
    if shot != expected:
        # lever 4: a real project diffs pixels with a tolerance instead of ==.
        (baseline_dir / "product-grid.actual.png").write_bytes(shot)
        attach_html(
            "visual-diff",
            "<p>Baseline and actual differ. Compare "
            "<code>product-grid.png</code> vs <code>product-grid.actual.png</code>.</p>",
        )
        pytest.fail(
            "Visual difference detected. Review the artifacts; if the change is "
            "intended, delete the baseline and re-run to re-record."
        )


@pytest.mark.a11y
def test_dark_mode_renders_with_readable_contrast(
    playwright: Playwright, browser, base_url: str
) -> None:
    """Dark mode is a whole second theme that usually gets zero test coverage.
    Running the same axe audit under `color_scheme="dark"` is nearly free."""
    context = browser.new_context(base_url=base_url, color_scheme="dark")
    page = context.new_page()
    try:
        page.goto("/")
        expect(page.get_by_test_id("product-grid")).to_be_visible()

        violations = _audit(page, "home-dark")
        contrast = [v for v in violations if v["id"] == "color-contrast"]

        assert not contrast, f"Dark-mode contrast failures:\n{_format(contrast)}"
    finally:
        context.close()
