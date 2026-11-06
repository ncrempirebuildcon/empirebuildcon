# L2 · Security review (Track A)

| | |
|---|---|
| **Task id** | `L2` |
| **Track** | A (Claude) |
| **Branch** | `fix/l2-security` |
| **Depends on** | `main` at or after `9e26435` |
| **Status** | Next for Claude |

## Goal

The Phase 8 security review, done before launch on the code as it is, with every finding either fixed or recorded with a reason. The owner gets a written report (`docs/` private copy plus a summary in the PR).

## Scope

1. **Sign-in and sessions:** password rules, lockout and rate limits, two-factor, session cookie flags, logout and expiry, password reset tokens, CSRF on every state-changing admin route.
2. **Permissions:** every admin route checked against its required permission; anyone else's lead stays 404; export limits.
3. **Public intake:** lead and site-visit forms (validation, honeypot, rate limit per network, consent stored), redirect hit endpoint (signature), revalidation endpoint.
4. **Uploads:** magic-byte checks, metadata stripping, Cloudinary signed uploads and confirm, sizes and types.
5. **Headers and CSP:** nonce CSP on every page, HSTS, frame, referrer, permissions policy; the edge key and client-IP handling (D-027).
6. **Dependencies and secrets:** `pnpm audit`, `uv`/`pip-audit`, a secrets scan of the repo and its history; the Dependabot state.
7. **Personal data:** what reaches logs, Sentry and emails (no phone or message in subjects or logs); erasure and retention jobs.

## Acceptance list

- [ ] Every scope item checked, with what was checked and how.
- [ ] Findings fixed with tests, or recorded with a reason and the owner's approval for anything left.
- [ ] Full checks green (pytest twice, e2e twice) and an independent reviewer pass.
- [ ] SECURITY.md updated; a decision number for any change in approach.
