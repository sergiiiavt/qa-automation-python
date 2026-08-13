# Task shortcuts. `make help` lists them.
# Windows users: run these through Git Bash, or copy the command out of the recipe.

PY ?= python
PYTEST ?= $(PY) -m pytest

.DEFAULT_GOAL := help
.PHONY: help install app smoke services web mobile-web mobile all parallel lint fmt report clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies and the Playwright browsers
	$(PY) -m pip install -e ".[bdd,lint]"
	$(PY) -m playwright install --with-deps chromium firefox webkit

app:  ## Run the demo app on http://127.0.0.1:8000 (docs at /docs)
	$(PY) -m uvicorn sut.app:app --reload --port 8000

smoke:  ## The gate: must stay under 2 minutes
	$(PYTEST) -m smoke -n auto

services:  ## API layer only — no browsers required
	$(PYTEST) tests/services -n auto

web:  ## Desktop browser tests
	$(PYTEST) tests/web -m "not mobile_web" -n auto

mobile-web:  ## Emulated mobile-web tests (fast, no device needed)
	$(PYTEST) tests/web -m mobile_web -n auto

mobile:  ## Native Appium tests (needs a running Appium server + device)
	$(PYTEST) tests/mobile

headed:  ## Watch the browser tests run — the fastest way to debug a UI failure
	$(PYTEST) tests/web --headed --slowmo 400 -x

trace:  ## Record traces + video for failures only, then: playwright show-trace artifacts/<test-nodeid>/trace.zip
	$(PYTEST) tests/web --tracing retain-on-failure --video retain-on-failure --output artifacts

all:  ## Everything that can run without a device
	$(PYTEST) tests -n auto

parallel:  ## Full suite across all cores with reruns, as CI runs it
	$(PYTEST) tests -n auto --reruns 1 --alluredir=allure-results

lint:  ## Static checks
	ruff check framework tests sut
	mypy framework

fmt:  ## Auto-format and auto-fix
	ruff format framework tests sut
	ruff check --fix framework tests sut

report:  ## Open the Allure report (requires the allure CLI)
	allure serve allure-results

clean:  ## Remove generated artifacts
	rm -rf artifacts allure-results allure-report .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
