# Module 0 — Curriculum and how to study this

## Who this is for

You can write Python (functions, classes, decorators, context managers) and you
have run `pytest` at least once. You do not need prior experience with
Playwright, Appium, or framework design.

## The honest premise

Most "test automation courses" teach you to write `driver.find_element(...)` and
stop. The hard parts of this job are not the API calls — they are:

- deciding **what** to automate and at **which layer**;
- designing abstractions that survive 300 tests and three years;
- making a suite that runs in parallel without eating itself;
- diagnosing flakiness instead of adding retries;
- producing evidence people actually act on.

This course spends most of its time there. The tool syntax is the easy 20%.

## The 8-week path

Each week is roughly 6–8 hours. The exercises in
[Module 10](10-exercises.md) are where the learning actually happens — reading
alone will not transfer.

| Week | Read | Do | You know it when |
|---|---|---|---|
| 1 | [M1 pytest](01-pytest-foundations.md) | Ex. 1–5 | You can explain fixture scope and why `xfail_strict` matters |
| 2 | [M2 architecture](02-architecture.md) | Ex. 6–8 | You can justify every layer boundary in `framework/` |
| 3 | [M3 services](03-services.md) | Ex. 9–14 | You can add a new endpoint's service object + tests in 30 min |
| 4 | [M4 web](04-web.md) | Ex. 15–19 | Your UI tests have zero sleeps and zero XPath |
| 5 | [M5 mobile](05-mobile.md) | Ex. 20–23 | You can argue emulation vs. real device with numbers |
| 6 | [M6 data](06-test-data.md) + [M8 flakiness](08-flakiness.md) | Ex. 24–26 | `pytest -n auto` is green ten times running |
| 7 | [M7 CI/reporting](07-ci-reporting.md) | Ex. 27–28 | A failing CI run tells you why without opening a terminal |
| 8 | [M9 strategy](09-strategy.md) | Ex. 29–30 | You can defend your automation plan to a sceptical manager |

## How to study each module

1. **Read the module.** ~20 minutes.
2. **Open the code it points at.** Every module names real files. Read them with
   the module open beside you; the code carries comments that explain *why*, and
   the docs explain *when*.
3. **Break it deliberately.** Delete a `strict=True`, change a scope from
   `function` to `session`, remove a `data-loaded` wait. Run the suite. Watch
   what breaks and how the failure reads. This is the fastest way to internalise
   why the rule exists.
4. **Do the exercises.** Check yourself against the acceptance criteria.

## The mental model to carry through all of it

Three questions, asked in this order, for every test you ever write:

1. **What is the risk?** If the answer is "none, but coverage", don't write it.
2. **What is the cheapest layer that can prove it?** Almost always lower than
   your first instinct.
3. **How will this fail?** If a failure message wouldn't tell a stranger what
   broke, the test is not finished.

## What "done" looks like

By the end you should be able to walk into a project with no automation and,
within two weeks, have:

- a layered framework with typed config and a real HTTP client;
- an API suite covering the business rules;
- a small, deliberately-chosen UI suite;
- a mobile-web strategy that costs almost nothing;
- CI that runs in parallel, publishes a trend report, and that the team trusts.

That is the actual job. Start with [Module 1](01-pytest-foundations.md).
