# Local setup

How to run the website, CMS and API on your own computer, and how to run the same checks CI runs. Everything here was run and verified on 22 Oct 2026.

## What you need

| Tool | Version | Why |
|---|---|---|
| Git | 2.40 or newer | Version control ([CONTRIBUTING.md](CONTRIBUTING.md)) |
| Node.js | 24 LTS (`.nvmrc`) | Web app, CMS UI, shared packages |
| pnpm | 12.14.0 (`packageManager` in `package.json`; `corepack enable` picks it up) | JavaScript workspace |
| Python | 3.14 (`.python-version`) | API and worker |
| uv | 0.13 or newer | Python packages; it installs Python 3.14 for you if needed |
| PostgreSQL | 18 with pgvector (Docker), or any local 16–18 | Database. Without pgvector everything works until Phase 7 (D-026). |

You don't need a cloud account to work locally. Shared services (Neon, Cloudinary, Resend, Sentry, Netlify, Google Cloud) belong to the owner.

## First run

```bash
git clone https://github.com/ncrempirebuildcon/empirebuildcon.git empire && cd empire   # private: ask the owner to add you

# 1. Settings: copy the example, then replace every "change-me" with fresh values
cp .env.example .env
uv --directory apps/api run empire-api gen-secrets   # prints new random values for YOUR .env

# 2. Database (pick one)
docker compose up -d db                                         # PostgreSQL 18 + pgvector, user/password empire/empire
docker compose exec db createdb -U empire empire_test           # second database, used by the API tests
#   …or use your own PostgreSQL: create databases empire_dev and empire_test owned by a user "empire"

# 3. Install
pnpm install
uv --directory apps/api sync

# 4. Schema and default data
uv --directory apps/api run alembic upgrade head
uv --directory apps/api run empire-api seed                    # feature flags + default settings; safe to repeat

# 5. A staff account for yourself (local only; reads the password from the keyboard)
uv --directory apps/api run empire-api create-user --email you@example.com --name "Your Name" --role super_admin --password-stdin
```

`create-superadmin` is the production way to create the owner's account. It prints a one-time setup link. The page that link opens (`/admin/setup`) arrives in Phase 4, so use `create-user` locally until then.

## Run it

Use two terminals:

```bash
uv --directory apps/api run uvicorn empire_api.main:app --reload --port 8000   # API (docs at http://localhost:8000/api/docs)
pnpm dev                                                                      # web on http://localhost:3000
```

- Open http://localhost:3000 for the site and http://localhost:3000/admin/login for the CMS.
- The browser only talks to port 3000. Next.js forwards `/api/*` to the API (ARCHITECTURE §3).
- Optional: `uv --directory apps/api run empire-worker` runs the background worker loop. On free hosting a scheduler calls the drain endpoint instead (D-010).

## Checks (the same as CI)

Run these before you push ([CONTRIBUTING.md](CONTRIBUTING.md) §6).

```bash
# Web, UI package, API client, QA
pnpm format:check
pnpm -r lint
pnpm -r typecheck
pnpm --filter @empire/ui test
pnpm --filter @empire/web build

# API (from apps/api; uses the empire_test database and wipes it)
cd apps/api
uv run ruff check && uv run ruff format --check
uv run mypy src
uv run pytest -q
cd ../..

# Contract: after changing any API route, regenerate and commit both files
pnpm api:openapi && pnpm api:client
git diff --exit-code -- packages/api-client

# Browser journeys and accessibility (build the web app first; starts the API and web app itself)
pnpm e2e
```

- `pnpm e2e` creates a throwaway staff account in `empire_dev` and generates its own test secrets.
- On a machine without the Playwright browser, run `pnpm --filter @empire/qa exec playwright install chromium` once.
- If a Chromium is already installed elsewhere, point `PW_CHROMIUM_PATH` at it instead.

## Where things are

See the repository map in [README.md](README.md#repository-map) and the README inside each app or package:
- [`apps/api`](../apps/api/README.md)
- [`apps/web`](../apps/web/README.md)
- [`packages/ui`](../packages/ui/README.md)
- [`packages/api-client`](../packages/api-client/README.md)
- [`qa`](../qa/README.md)

## Common problems

| Problem | Fix |
|---|---|
| `pnpm install` stops because of build scripts | Allowed build scripts are listed under `allowBuilds` in `pnpm-workspace.yaml`. Add a new one only after checking the package. |
| The API refuses to start: "placeholder secret" | Run `empire-api gen-secrets` and put real local values in `.env`. In staging and production the API refuses placeholders on purpose. |
| Signing in on `http://localhost` doesn't stick | Use `localhost`, not `127.0.0.1`. Browsers treat `localhost` as secure, which the `__Host-` session cookie needs. |
| The API tests wiped my data | They always use `empire_test` (or `TEST_DATABASE_URL`). Never point that at a database you care about. |
