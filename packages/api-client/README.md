# @empire/api-client

Typed client for the Empire API. Types are **generated** from the API's OpenAPI document; the API code is the source of truth from Phase 3 ([D-020](../../handbook/DECISIONS.md)).

```bash
pnpm api:openapi   # (root) export packages/api-client/openapi.json from the FastAPI app
pnpm api:client    # (root) regenerate src/schema.d.ts from it
pnpm --filter @empire/api-client generate -- ../../handbook/api/openapi-v1.yaml  # from another file
pnpm --filter @empire/api-client generate:check   # CI: fails if the types are stale
```

```ts
import { createApiClient, unwrap } from "@empire/api-client";

const api = createApiClient();                       // browser: same-origin /api/*
const me = unwrap(await api.GET("/api/v1/auth/me"));
api.setCsrfToken(me.csrf_token);                     // writes now send X-CSRF-Token
await api.POST("/api/v1/auth/logout");
```

## Rules

- `src/schema.d.ts` and `openapi.json` are generated: never edit them by hand.
- The CSRF token is kept in memory only. Never put tokens or session data in browser storage (handbook/SECURITY.md).
- Errors are RFC 9457 problem+json; `unwrap()` throws `ProblemError` with `status` and per-field messages.
