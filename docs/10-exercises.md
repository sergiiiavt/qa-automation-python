# Module 10 — Exercises

Thirty graded tasks against the bundled demo app. Each has acceptance criteria,
so you can check yourself.

Run the app on the side while you work:

```bash
uvicorn sut.app:app --reload
```

`http://127.0.0.1:8000` for the UI, `/docs` for the interactive API reference.

---

## Level 1 — pytest foundations (1–5)

**1. Fixture scopes.** Add a `print` to `sut`, `api_client` and `shop`, then run
`pytest tests/services -s --setup-show`. Draw the construction order for three
tests.
*Accept:* you can explain why `sut` prints once and `api_client` prints three times.

**2. Fixture failure.** Make `shop_as_user` raise before `yield`. Run a test that
uses it. Observe whether the teardown ran.
*Accept:* you can state the rule and name the mitigation used in this repo.

**3. Parametrize a table.** Write `test_rating_is_within_range` covering products
0–7 (including nonexistent ids), with a `case` label on each row.
*Accept:* failures print a readable case name; nonexistent ids expect 404.

**4. Markers.** Add a `payments` marker, declare it in `pyproject.toml`, apply it
to the order tests, then run `pytest -m "payments and not slow"`.
*Accept:* `pytest -m paymnets` (typo) **fails**, not silently selects zero.

**5. A hook.** Write a `pytest_terminal_summary` hook that prints the three
slowest tests and the total count by marker.
*Accept:* output appears after the standard summary on every run.

---

## Level 2 — architecture (6–8)

**6. Find the violation.** Write a test that imports `httpx` directly and asserts
on `response.json()["total"]`. Then rewrite it through the service objects.
*Accept:* you can name which layer rule the first version broke and what it costs.

**7. A new service object.** Add `POST /api/products/{id}/reviews` to the SUT
(rating 1–5, comment ≤ 500 chars), then a `ReviewsApi` with both the typed and
raw method styles, plus a `Review` model.
*Accept:* `shop.reviews.create(...)` returns a typed model; boundary tests use the
`_raw` variant.

**8. A component object.** Add a "quantity stepper" (+ / − / value) to a cart row
in the SUT, then model it as a component class scoped to the row.
*Accept:* `cart.row_component("Aurora Headphones").increment()` works and no test
contains a raw selector.

---

## Level 3 — services (9–14)

**9. The full checklist.** Apply the [Module 3](03-services.md) test-design
checklist to `POST /api/auth/register`.
*Accept:* ≥ 10 tests covering happy path, duplicate username, boundaries, wrong
types, and no 500 on any malformed input.

**10. Find a real bug.** `POST /api/cart/items` merges quantities and caps at 99.
Write tests that probe the cap. What happens at exactly 99 + 1?
*Accept:* you can state the actual behaviour and argue whether it is correct.

**11. BOLA sweep.** Write the authorization matrix from Module 3 for
`GET /api/orders/{id}` **and** `GET /api/cart`.
*Accept:* the orders test fails and is marked `xfail(strict=True)` with a ticket.

**12. Contract expansion.** Add `POST /api/products/{id}/reviews` (from Ex. 7) to
the SUT, run the Schemathesis test, and triage every finding.
*Accept:* a written verdict per finding — real bug, spec gap, or tool artefact —
and any exclusion carries its reason in a comment.

**13. A property.** State and test a property about the search endpoint that is
not already covered.
*Hint:* filtering is monotonic — narrowing a query can never add results.
*Accept:* a Hypothesis test that fails if you break the filter logic in the SUT.

**14. Test the framework.** Using `respx`, prove that `ApiClient` redacts the
`Authorization` header from its attachments.
*Accept:* the test fails if you remove `SENSITIVE` from `client.py`.

---

## Level 4 — web (15–19)

**15. Locator refactor.** Rewrite `test_product_grid_renders_the_catalogue` using
only `get_by_role` and `get_by_label`. Note what you cannot reach.
*Accept:* you can list which elements lack an accessible role and why that is
itself a finding.

**16. A new page.** Add an order-history page to the SUT (`/orders`), then a
`OrdersPage` Page Object and three tests.
*Accept:* the Page Object has a `ready_locator`, and `open()` never returns before
the page is rendered.

**17. Fault injection.** Use `page.route` to make `/api/products` return `[]`,
then a `500`, then hang for 30 s. Assert the UI behaves acceptably in each case.
*Accept:* three tests; at least one documents a genuine UX gap in the demo app.

**18. Delete the waits.** Remove the `data-loaded` attribute from the SUT and make
the tests pass again without it. Then put it back.
*Accept:* you can articulate what you had to give up (and why asking developers
for the hook is worth it).

**19. Visual baseline.** Run the visual test, commit the baseline, change the
card padding in the CSS, run again.
*Accept:* the diff is detected and you can explain each of the four
stabilisation levers.

---

## Level 5 — mobile (20–23)

**20. Extend the device matrix.** Add two devices to `DEVICES` and get the whole
file green.
*Accept:* the tablet skips are correct and no test hardcodes a viewport width.

**21. Find a responsive bug.** Add a wide element to the SUT (a table, or a long
unbroken string) and confirm the overflow test catches it. Then fix the CSS.
*Accept:* red → fix → green, and you can name the CSS property that fixed it.

**22a. Verify the bundled screens yourself.** Install Appium 3 + UiAutomator2,
start `appium` and `npx @appium/inspector`, point Inspector at
`apps/mda-2.2.0-25.apk` with the same capabilities `driver_factory.py` builds,
and confirm every locator in `CatalogScreen`, `MenuScreen` and `LoginScreen`
against what Inspector actually reports.
*Accept:* you can point at the exact attribute (resource-id or content-desc)
each locator in `framework/mobile/screens.py` was built from.

**22b. Build the screens this course deliberately left out.** Using Appium
Inspector, find the real locators for the product-detail screen, the
add-to-cart control, and the cart/checkout screens of the bundled app. Add a
`ProductDetailScreen` and a `CartScreen` to `framework/mobile/screens.py`
following the existing style, plus tests in `tests/mobile/test_native_app.py`
for adding an item and completing checkout.
*Accept:* every new locator was confirmed in Inspector, not guessed from the
visible UI; the tests pass against a real emulator running the bundled APK.

**23. Device-only scenarios.** From the list in [Module 5](05-mobile.md), add
one more test — for a scenario not already covered in
`tests/mobile/test_native_app.py` — for either the hardware back button or
network loss.
*Accept:* the docstring states what it proves that no web test could, and the
locators used are ones you verified in Exercise 22a rather than reused blind.

---

## Level 6 — data and flakiness (24–26)

**24. Reproduce the collision.** Revert `shop_as_user` to use
`persona("standard")`. Run `pytest tests/services -n 4` several times.
*Accept:* you reproduce the failure, and can explain why it moves between tests.

**25. Fix it three ways.** Fix Ex. 24 with (a) per-worker accounts, (b)
`--dist loadgroup` + `xdist_group`, (c) a per-test namespace.
*Accept:* all three are green; you can rank them and justify the ranking.

**26. Diagnose a plant.** Insert a deliberate flake (a 50%-probability race in
the SUT's JS), then find it using only the artifacts the framework produces.
*Accept:* you identify the root cause without reading your own plant code.

---

## Level 7 — CI and strategy (27–30)

**27. Pipeline surgery.** Add a job that runs only `-m "a11y"` and publishes the
axe report as an artifact — non-blocking.
*Accept:* the job runs on PRs, never blocks a merge, and its artifact is
downloadable.

**28. Trend reporting.** Run the suite five times with `--alluredir`, generate a
report with history, and identify the slowest and least stable tests.
*Accept:* you can name your top-3 flake candidates from the data, not intuition.

**29. Risk assessment.** Build the risk table from [Module 9](09-strategy.md) for
the demo app: every feature, scored, with the layer you'd cover it at.
*Accept:* one page, defensible, and at least one row says "no automation".

**30. The pitch.** Write a one-page proposal for automating a real project you
know. Include: current cost, proposed layers, 12-week plan, the metrics you'll
report, and what you will *not* automate.
*Accept:* a non-technical manager could read it and decide.

---

## Stretch: things this framework does not have yet

Genuinely useful additions, roughly in value order:

- **BDD layer.** Add `pytest-bdd` (already in the `bdd` extra) over the existing
  Page Objects for the checkout flow. Then write down honestly whether the
  Gherkin earned its keep — often it does not unless non-engineers actually read it.
- **Performance smoke.** Assert p95 latency per endpoint across a 50-request loop
  and fail on regression against a stored baseline.
- **Load testing.** Drive Locust through the same service objects.
- **Consumer-driven contracts.** Pact between two services, so the provider's
  pipeline breaks when it breaks *you*.
- **Mutation testing.** Run `mutmut` against `framework/` — it measures whether
  your tests actually *verify* anything, which coverage never does.
- **Security scanning.** ZAP baseline scan against the SUT in CI.
- **Test impact analysis.** Map tests to code paths and run only what a diff
  affects.
- **AI-assisted locator healing.** Evaluate it honestly: it papers over the
  symptom (unstable locators) rather than the cause, and it can mask real
  regressions. Worth understanding, rarely worth adopting.
