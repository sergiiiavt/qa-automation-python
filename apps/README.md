# apps/

`mda-2.2.0-25.apk` is the official open-source **Sauce Labs "My Demo App"** for
Android: https://github.com/saucelabs/my-demo-app-android — MIT licensed,
redistributed here unmodified so the native-mobile module runs offline like
the rest of this course, with no download step and no account.

It ships as an APK rather than source because that is what Appium actually
installs and drives; the source repository is linked above for anyone who
wants to read what the app does instead of just reverse-engineering it from
the UI.

## Why this app

- **Real and verified.** Every locator in [framework/mobile/screens.py](../framework/mobile/screens.py)
  was confirmed against this exact build, not invented. Compare that against
  most "sample mobile framework" repos online, where the locators are
  illustrative and nothing actually runs.
- **A shape that matches this course's web layer.** It has a product catalog,
  a login flow behind a hamburger menu, and a cart/checkout — the same
  domain [sut/](../sut) uses, which makes the cross-layer lessons in
  [docs/05-mobile.md](../docs/05-mobile.md) easy to follow even though this
  app is unrelated to the bundled FastAPI service.
- **Small.** 18 MB, well under any git hosting limit.

## Credentials

The app ships with three fixed accounts, documented in Sauce Labs' own repo:

| Username | Password | Behaviour |
|---|---|---|
| `bod@example.com` | `10203040` | Logs in successfully |
| `alice@example.com` | *(anything)* | Locked out — a password-field error |
| *(blank)* | — | A username-required validation error |

## What is verified here, and what is not

The Catalog (landing) screen, the hamburger menu, and the Login screen have
confirmed, working locators. **The product-detail, add-to-cart and checkout
screens do not** — nobody had verified their resource ids before this course
was written, and this repo does not ship locators nobody checked. Wiring
those up, using Appium Inspector to find the real ids yourself, is
[Exercise 22b](../docs/10-exercises.md#level-5--mobile-20-23) — building a
`CartScreen` against a real app is a more useful exercise than reading one
somebody else already built.

## Provenance

This exact binary is the release asset GitHub built for the upstream `2.2.0`
tag (commit `36b012eecdf6a2b488b9504e16b3d0c3ca9a0e7b`), released 2024-11-14 —
not something downloaded from a random mirror. The nightly `build-mobile-app`
job in [.github/workflows/ci.yml](../.github/workflows/ci.yml) additionally
compiles that same pinned commit from source and tests *that* fresh build
instead of this committed one, so the pipeline exercises a real build stage
rather than only ever installing a static file. See
["The full pipeline"](../docs/05-mobile.md#the-full-pipeline-a-real-build-stage-not-just-a-bundled-binary)
in Module 5 for why the commit is pinned rather than tracking upstream's
default branch.

## Using your own app instead

Drop your `.apk` (Android) or `.app`/`.ipa` (iOS) here, then either set
`QA_APP_PATH` in `.env` or pass `--app-path` — see
[framework/config.py](../framework/config.py). Every screen object and test
in `tests/mobile/` will need new locators; nothing about the framework
(`BaseScreen`, the driver factory, the fixtures) is specific to this app.
