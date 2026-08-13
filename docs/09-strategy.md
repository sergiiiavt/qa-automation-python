# Module 9 — Strategy and metrics

Everything so far was *how*. This module is *what* and *why* — the part that
separates an automation engineer from a script writer.

---

## Where tests belong

The pyramid is a useful default and a bad law. The useful version is a question:

> **What is the cheapest layer that can prove this?**

| Layer | Cost/test | Runtime | Finds | Share |
|---|---|---|---|---|
| Unit (dev-owned) | minutes | ms | Logic errors | 60–70% |
| **Services / API** | ~15 min | ~100 ms | Business rules, auth, integration | **20–30%** |
| **UI (web/mobile)** | 1–2 h | 2–30 s | Rendering, wiring, journeys | **5–10%** |
| Manual/exploratory | — | — | The bugs nobody predicted | ongoing |

In this repo: 90 API tests, 60 web tests, 15 mobile tests. The API layer runs in
11 seconds and carries most of the risk coverage.

### The trap

Teams automate at the UI layer because it maps to a manual test case, and because
"end-to-end" sounds thorough. Result: 400 UI tests, a 90-minute build, 30 flaky
failures a week, and a team that stops looking. Every one of those tests had a
cheaper equivalent one layer down.

**Before writing any UI test, ask what it proves that an API test could not.**
If there is no answer, write the API test.

---

## What to automate

Score each candidate. High score → automate first.

| Factor | High value | Low value |
|---|---|---|
| **Risk** | Payment, auth, data loss, compliance | Cosmetic |
| **Frequency** | Every release | Once a year |
| **Repetition** | Same steps, many data sets | Different each time |
| **Determinism** | Same input → same output | Depends on judgement |
| **Cost to test manually** | 30 min of clicking | 10 seconds |
| **Stability** | Feature is settled | Redesigned monthly |

### Do not automate

- **UI that is still being designed.** You will rewrite the test three times.
  Wait for the second iteration.
- **One-off migrations.** Test them manually, once.
- **Anything requiring human judgement.** "Does this look right?" "Is the copy
  clear?"
- **Exploratory testing.** Automation checks known expectations; it cannot be
  surprised. You still need humans who can be.
- **Coverage for its own sake.** A test with no risk behind it is pure
  maintenance cost.

---

## Metrics that mean something

### Use these

| Metric | Target | Why |
|---|---|---|
| **Escaped defects** | Trending down | The only metric that measures the actual goal |
| **Flake rate** | < 1% | Trust. Above 5% the suite is decorative |
| **Suite runtime** | < 10 min for the PR gate | Above that, people stop waiting and start merging blind |
| **Time to diagnose a failure** | < 5 min | Measures your reporting, which is a real deliverable |
| **Defects found by layer** | API ≫ UI | If UI finds most bugs, your API layer is too thin |
| **Mean time to fix a broken build** | < 1 h | Measures whether people trust the signal |

### Be careful with these

**Coverage percentage.** Useful as a *discovery* tool ("nothing covers the refund
path?"), dangerous as a *target*. Coverage measures execution, not verification —
a test with no assertions raises coverage. Goodhart's law applies hard here.

**Test count.** More tests is not better. 400 tests covering the same login flow
is worse than 40 well-chosen ones: more runtime, more maintenance, more flake,
no more risk covered.

**Automation percentage.** "We automated 90% of test cases" says nothing about
whether the 10% left is where all the risk lives.

---

## Risk-based prioritisation

Score each feature: **Risk = Probability of failure × Impact of failure**.

| Feature | Prob | Impact | Score | Coverage |
|---|---|---|---|---|
| Checkout / payment | 3 | 5 | **15** | API exhaustive + UI journey + mobile smoke |
| Authentication | 3 | 5 | **15** | API exhaustive incl. BOLA + one UI test |
| Cart maths | 4 | 4 | **16** | API exhaustive + property-based |
| Product search | 4 | 2 | 8 | API + one UI test |
| Footer links | 1 | 1 | 1 | None |

This table is the artifact to bring to a planning meeting. It converts "we need
more tests" into a defensible, negotiable plan.

---

## Building a framework from zero: the 12-week plan

**Weeks 1–2 — Foundations.** Repo, typed config, HTTP client, CI skeleton. One
green smoke test end to end in CI. *Ship this before writing 50 tests.*

**Weeks 3–5 — Services layer.** Service objects for the critical endpoints. The
whole test-design checklist from [Module 3](03-services.md) applied to the two
highest-risk flows. Contract testing wired up.

**Weeks 6–8 — Web layer.** Page Objects for the critical journeys. `storage_state`
auth. API seeding. **Five to ten** end-to-end tests, not fifty. Emulated
mobile-web comes almost free at this point.

**Weeks 9–10 — Mobile.** Emulated mobile web in the PR gate. Appium native smoke
nightly, if there is an app.

**Weeks 11–12 — Hardening.** Parallel execution, flake hunt, Allure history,
quarantine process, documentation.

### The order matters

Most failed automation projects invert it: they write 200 UI tests first, then
try to add CI, then discover nothing runs in parallel. Foundations → cheap layer
→ expensive layer → hardening.

---

## Making the case to management

Speak in their units.

**Bad:** "We have 500 automated tests and 80% coverage."

**Good:** "Regression testing for a release took 3 engineer-days. It now takes
40 minutes and runs on every commit. In the last quarter the suite caught 14
defects before merge, including an authorization bug that exposed other users'
orders. Escaped defects are down from 9 to 3 per release."

**What to report monthly:** escaped defects (trend), defects caught pre-merge,
suite runtime, flake rate, and a one-line note on what you fixed in the suite
itself.

**What not to report:** test counts, coverage percentage, lines of test code.

---

## Skills roadmap

**Foundation** — Python, pytest, HTTP, Git, CI, one UI tool.

**Professional** — framework design, contract testing, parallel execution, flake
diagnosis, reporting, Docker, test strategy.

**Senior** — property-based testing, performance testing (Locust/k6), security
basics (OWASP API Top 10), observability-driven testing, mentoring, and the
ability to say *"we should not automate that"* and defend it.

**The differentiator is rarely tooling.** It is judgement about what to test and
where, and the ability to explain that judgement to people who control budget.

---

## Enhancements worth proposing on a real project

Ranked by value ÷ effort, based on what this repo demonstrates:

1. **Ask for a test-data creation API.** Unblocks parallelism permanently.
   Usually an afternoon of backend work.
2. **Ask for `data-testid` attributes.** Kills a whole class of locator churn.
3. **Ask for accessibility ids on mobile.** One locator for both platforms.
4. **Contract testing in the backend's own pipeline.** Catches drift before it
   reaches you.
5. **Emulated mobile web on every commit.** Nearly free, high yield.
6. **Allure history from day one.** Four lines of YAML; without it you have
   snapshots instead of trends.
7. **A11y gate at serious/critical.** Cheap, and increasingly a legal requirement.
8. **Redact secrets in reports.** One function. Prevents a real incident.
9. **`filterwarnings = ["error"]`.** Turns next year's breakage into today's
   small fix.
10. **A weekly flake review.** Fifteen minutes. Compounds.

---

## Checkpoint

1. Why is coverage percentage a bad target and a good discovery tool?
2. A stakeholder wants "everything automated". Your response?
3. Which two metrics would you put on a monthly report to a VP?
4. Why does the 12-week plan put CI in week 1 rather than week 11?
5. Name three things you would ask developers for in your first month.

Next: [Module 10 — Exercises](10-exercises.md)
