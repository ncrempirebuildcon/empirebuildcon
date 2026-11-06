# Empire API image for Google Cloud Run (task L3, RUNBOOK.md). One image, three commands:
#   - the API (default CMD), Cloud Run service;
#   - migrations:  alembic upgrade head        (Cloud Run job, before each deploy);
#   - admin CLI:   empire-api create-superadmin (Cloud Run job, once, for the owner).
# The background work runs through Cloud Scheduler calling /api/v1/internal/outbox/drain (D-010).
#
# Build from this folder:  docker build -t empire-api apps/api
# Versions are pinned exactly (D-006); Dependabot's docker ecosystem proposes updates.

# Keep uv in step with UV_VERSION in .github/workflows/ci.yml.
FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM python:3.15.0-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.15.0-slim
# SECURITY: runs as an unprivileged user with no shell login and no write access to the code.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin empire
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/alembic.ini /app/alembic.ini
COPY --from=build /app/migrations /app/migrations
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080
USER 10001
EXPOSE 8080
# SECURITY (D-052, SECURITY.md §8): no uvicorn access log (it would print query strings, such as
# a lead search); the app logs each request itself, path only. No proxy headers: the visitor's
# IP comes only from the web proxy's signed edge headers (D-027), never X-Forwarded-For.
# Cloud Run kills the container 10 s after SIGTERM, so requests get 8 s to finish.
CMD ["sh", "-c", "exec uvicorn empire_api.main:app --host 0.0.0.0 --port \"$PORT\" --no-access-log --no-proxy-headers --timeout-graceful-shutdown 8"]
