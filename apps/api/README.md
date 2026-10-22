# empire-api

The Empire API (FastAPI), its background worker and the `empire-api` admin CLI. One Python package, `empire_api`, with two entry points (D-010).

Read [`../../handbook/README.md`](../../handbook/README.md) first. The rules for code and comments are in [`CODE_STYLE.md`](../../handbook/CODE_STYLE.md); the design is in [`ARCHITECTURE.md`](../../handbook/ARCHITECTURE.md) and [`SECURITY.md`](../../handbook/SECURITY.md).

## Layout

```
apps/api/
├─ pyproject.toml          pinned dependencies (D-006), ruff/mypy/pytest settings
├─ uv.lock                 exact versions; commit it
├─ alembic.ini, migrations/   database migrations (0001_foundation = Phase 3 tables,
│                          0002_catalogue = projects, their children, cities, localities, amenities)
├─ scripts/                make_common_passwords.py (regenerates the weak-password list)
├─ src/empire_api/
│  ├─ main.py              create_app(): routers, middleware, error handlers, OpenAPI tweaks
│  ├─ config.py            Settings from env vars; refuses unsafe secrets in staging/production
│  ├─ db.py                engine, sessions, declarative Base (UUID v7, timestamptz)
│  ├─ errors.py            RFC 9457 problem+json for every error
│  ├─ logs.py              structured JSON logs, phone masking
│  ├─ health.py            /api/health/live (no DB) and /api/health (DB check)
│  ├─ middleware/          trailing-slash strip (no redirects), request id, security headers
│  ├─ platform/            audit log, outbox writer, PostgreSQL rate limits, crypto helpers
│  ├─ users/               sign-in, sessions, CSRF, passwords, roles matrix, staff admin
│  ├─ site_settings/       feature flags, default settings groups
│  ├─ projects/            projects, towers, configurations, … and the catalogue (Phase 4)
│  │  ├─ models.py         tables (0002_catalogue); vocab.py = the allowed values (enums)
│  │  ├─ schemas*.py       request/response shapes: shared values, project, children, catalogue
│  │  ├─ fields.py         bounded string/number types for request bodies (SECURITY.md §5)
│  │  ├─ common.py         audit diffs, outbox events, project lock, slugs, 409 on clashes
│  │  ├─ service.py        list, create, update/archive, delete, publish, unpublish;
│  │  │                    duplicate.py copies a project with its children
│  │  ├─ project_input.py  body → columns and the rules across fields (ranges, pin, locality)
│  │  ├─ children.py       the five operations for every child list; child_kinds.py = per kind
│  │  ├─ catalogue.py      cities, localities, amenities ("used by N projects" guards)
│  │  ├─ blockers.py       publish blockers: the one place that decides "ready to publish"
│  │  ├─ present.py        rows → responses; display.py = ₹ and area strings (twin of
│  │  │                    packages/ui/src/format, same test vectors)
│  │  ├─ maps.py           Google Maps pin resolver (SSRF rules in its header); pluscode.py
│  │  ├─ routes.py, routes_children.py, routes_catalogue.py   HTTP only
│  │  └─ seed.py           amenity catalogue and `seed --sample` (D-015)
│  ├─ media/               contract shapes Media and LinkedMedia (the module arrives in part 2)
│  ├─ integrations/        outbox drain + handlers, internal drain endpoint
│  ├─ worker.py            empire-worker loop (paid always-on hosting)
│  └─ cli.py               empire-api commands
└─ tests/                  pytest against a real PostgreSQL database
```

## Commands

Run everything from `apps/api/`. The root `.python-version` makes uv use Python 3.14.

```bash
uv sync                                        # install (creates .venv)
uv run alembic upgrade head                    # migrate the database in DATABASE_URL
uv run empire-api seed                         # flags, settings, amenity catalogue (idempotent)
uv run empire-api seed --sample                # + "Sample — Project A/B" (dev/demo only; refused in production)
uv run uvicorn empire_api.main:app --reload    # API on http://localhost:8000 (docs at /api/docs)
uv run empire-worker                           # optional: worker loop (drain + daily clean-up)

uv run ruff check && uv run ruff format --check
uv run mypy src                                # strict
uv run pytest -q                               # needs PostgreSQL; see "Tests" below
uv export --frozen --no-emit-project --all-groups -o /tmp/req.txt && uv run pip-audit -r /tmp/req.txt --disable-pip --strict   # known vulnerabilities (same as CI)

uv run empire-api gen-secrets                  # fresh values for YOUR local .env
uv run empire-api create-superadmin --email admin@empirebuildcon.com   # once per environment
uv run empire-api openapi --out ../../packages/api-client/openapi.json  # after changing routes
```

`create-superadmin` prints a one-time setup link (24 hours). Nobody ever types a password for someone else; staff invited from the CMS get the same kind of link.

## Tests

The tests use a real PostgreSQL database, by default `postgresql+psycopg://empire:empire@localhost:5432/empire_test`; set `TEST_DATABASE_URL` to use another. The first test drops and recreates the `public` schema, so **never point it at a database you care about**. Then it runs the migrations, and every test starts from empty tables.

Important guards:
- `test_no_route_ever_redirects` calls every route with and without a trailing slash and fails on any 3xx. This is the Current Investor bug (ARCHITECTURE §3).
- `test_every_route_declares_who_may_call_it` fails if a route has no permission marker.
- `test_models_match_the_migrated_database` fails if a model changed without a migration.
- `test_projects_and_catalogue_match_the_design_contract` fails if a Projects or Catalogue operation drifts from `handbook/api/openapi-v1.yaml` (method, path, operationId, permission).
- `tests/test_display.py` runs the same money and area vectors as `packages/ui/test/format.test.ts`; change both together.

Fixtures worth knowing (tests/conftest.py):
- `no_network` (automatic): the maps resolver's real HTTP client fails any test that reaches it. Short-link tests inject a fake client (`httpx.MockTransport`).
- `qr_present`: pretends every project has its RERA QR image, so publish can be tested before the media manager (part 2) exists. Without it, "RERA QR code missing" always blocks publishing.

## Adding a staff route

```python
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.platform import audit, outbox
from empire_api.platform.crypto import client_ip
from empire_api.users.deps import require, staff
from empire_api.users.sessions import SessionInfo

router = APIRouter(prefix="/api/v1/admin", tags=["Things"],
                   responses=problem_responses(401, 403, 404, 422))

@router.patch("/things/{key}", operation_id="update_thing", **staff("things.write", write=True))
def update_thing(key: str, body: ThingUpdate, request: Request,
                 actor: Annotated[SessionInfo, Depends(require("things.write"))],
                 db: Annotated[Session, Depends(get_db)]) -> Thing:
    ...change the row...
    audit.record(db, action="thing.updated", entity_type="thing", entity_id=key,
                 actor_id=actor.user.id, ip=client_ip(request), changes=audit.diff(before, after))
    outbox.emit(db, type_="thing.updated", aggregate_type="thing", aggregate_id=key,
                actor_id=actor.user.id, data={"key": key})
    db.commit()      # one commit: change + audit row + event together
```

Checklist for a new route:
1. **Permission.** Use `staff(...)`: it both enforces the permission and publishes it in the spec. Take `require(...)` as a parameter only when you need the signed-in user (it runs once per request). The permission must exist in `users/roles.py`; adding one or changing a role needs owner approval (CONTRIBUTING §7).
2. **Public routes.** Use `**PUBLIC` instead, and add rate limits (`platform.rate_limit.enforce`).
3. **Request bodies.** Staff bodies use `extra="forbid"`, and every string has a length limit.
4. **Audit and events.** Write an audit row for every create, update, delete, publish and export, and an outbox event for anything others react to (ARCHITECTURE §9).
5. **Spec.** Run `empire-api openapi` and regenerate the web client (`pnpm api:client` at the repo root). CI fails if the committed spec is stale.
6. **Tests.** Cover success, validation and permission denied.

## Configuration

All settings are environment variables. They are listed in the repo's `.env.example` and in SECURITY.md §7. The API-only extras are:

| Variable | Default | Meaning |
|---|---|---|
| `EDGE_PROXY_KEY` | empty | Shared secret with the web proxy (`apps/web/src/proxy.ts`). When set, calls without it get 403 (except health checks and `/api/v1/internal/*`), and only then is the client IP read from `X-Empire-Client-IP`. Empty locally; required in staging and production (D-027). `X-Forwarded-For` is never trusted. |
| `DB_POOL_SIZE` | `5` | Connections per process |
| `WORKER_DRAIN_INTERVAL_SECONDS` | `30` | Tick length of `empire-worker` |

The maps resolver (`POST /api/v1/admin/maps/resolve`) needs outbound HTTPS to Google's short-link hosts only (`maps.app.goo.gl`, `goo.gl`); long links and plus codes are read without any network call.

In development and test, missing secrets fall back to clearly insecure defaults so the app runs on a fresh clone. In staging and production, the app refuses to start without real values.
