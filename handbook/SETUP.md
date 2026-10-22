# Local setup

**Status:** there is no application code yet. It arrives in Phase 3. This page lists what you will need, so you can get your machine ready. Phase 3 replaces the "planned" commands with the real ones and ticks them off.

## What you need

| Tool | Version | Why |
|---|---|---|
| Git | 2.40 or newer | Version control ([CONTRIBUTING.md](CONTRIBUTING.md)) |
| Node.js | 24 LTS ([D-006](DECISIONS.md)) | Web app and CMS UI |
| pnpm | 12.x | JavaScript workspace manager |
| Python | 3.14 | API and worker |
| uv | 0.13.x | Python packages and lockfile |
| PostgreSQL | 17 or 18, matching the host | Database: Docker (`docker compose up db`) or a local install |

Optional:
- VS Code with the extensions listed in `.vscode/extensions.json`, added in Phase 3.
- Docker Desktop, used only for the local database.

## Planned first run (Phase 3 will confirm these)

```bash
git clone <repo URL from the owner>
cd <repo>
cp .env.example .env            # fill in local values only; never commit .env
pnpm install                    # web, CMS, shared packages
uv sync                         # API and worker
docker compose up -d db         # or point DATABASE_URL at a local PostgreSQL
uv run alembic upgrade head     # create the schema
uv run empire-api seed --sample # sample data, flagged is_sample
pnpm dev                        # web on http://localhost:3000, API on http://localhost:8000
```

## Accounts

- You don't need any cloud account to work locally.
- Shared services (Neon, Cloudinary, Resend, Sentry, Netlify and Google Cloud) belong to the owner. Ask for access to what you need, and never share keys in chat or commits.
