# Start from Playwright's own image: it ships the exact browser builds and the
# system libraries + fonts they need. Installing browsers onto a bare python
# image is a long, fragile detour that this one line avoids.
# Keep the tag pinned to the same version as the `playwright` package —
# a mismatch between the driver and the browser build is a real failure mode.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC

WORKDIR /app

# Copy the dependency manifest first so the (slow) install layer is cached and
# only re-runs when dependencies actually change.
COPY pyproject.toml ./
COPY framework ./framework
COPY sut ./sut
RUN pip install -e .

COPY conftest.py Makefile ./
COPY config ./config
COPY tests ./tests

# Non-root: browsers refuse to run sandboxed as root, and the usual workaround
# (--no-sandbox) weakens the very isolation you want in CI.
RUN chown -R pwuser:pwuser /app
USER pwuser

CMD ["pytest", "tests", "-n", "auto"]
