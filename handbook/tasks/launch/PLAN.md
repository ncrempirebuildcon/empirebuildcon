# Launch · plan

**Goal:** `https://empirebuildcon.com` live with real projects, as soon as the company's content and approvals are in. The website, CMS, database and API are built (Phases 3–5). This plan replaces the old phase order for the time until go-live (owner's decision, 6 Nov 2026, D-050).

**Order:**
1. **Inputs from the company** (owner hands out the forms in `docs/launch/`):
   - real project content (`Empire_Project_Content_Form.xlsx`);
   - Google Cloud billing approval (`Empire_Google_Cloud_Billing_Approval.xlsx`);
   - legal facts and a reviewer (`Empire_Legal_Review.xlsx`).
2. **Launch work** (the tasks below, in parallel with step 1).
3. **Go-live** (Phase 9 of the original plan): staging, production, DNS, Search Console, the production smoke test, then the owner's go-live approval.

**After launch:** Phase 6 (marketing tags, webhooks, campaign pages, UTM report), Phase 7 (AI chat and CMS helpers), Phase 10 (full handover docs).

**Who builds it:** the same two tracks as Phase 5 (D-040, [../../agents/WORKFLOW.md](../../agents/WORKFLOW.md)). Track A is Claude and Track B is the developer agent; Claude reviews both. Track B doesn't change `apps/api`, migrations, `proxy.ts`, `next.config.ts` or the shell unless its task doc says so.

## Tasks

| Task | Track | What | Needs | State |
|---|---|---|---|---|
| **L1** Steady tests and small fixes | B | Find and fix why admin e2e tests fail under load (the API answers "socket hang up"), the /saved remove message, `.env.example` | — | **Ready**, [L1-steady-tests.md](L1-steady-tests.md) |
| **L2** Security review | A | Phase 8's security review on the code as it is: auth, permissions, uploads, rate limits, headers, dependency audit, secrets scan; fixes for anything found | — | **Next for Claude**, [L2-security-review.md](L2-security-review.md) |
| **L3** Ready to deploy | A | Container image for the API (Cloud Run), Netlify config, migrations at deploy, the full environment-variable list, staging RUNBOOK. No account is touched | — | After L2 |
| **L4** Short CMS guide | A | How staff add a project, homes, photos and RERA, publish, and handle leads (with screenshots) | — | After L3 |
| **L5** Content import | A | Turn the filled project form into CMS entries (a checked import, or staff enter it with the guide) | Content form back | Waiting for content |
| **L6** Legal drafts | A | Privacy policy, terms, disclaimer, consent texts from the company facts; the reviewer approves (owner item o-20) | Legal facts back | Waiting for facts |
| **L7** Pre-launch checks | A | Phase 8 content review on real content, backup restore test, load test of lead intake and list pages, full test run | L3, L5, L6 | Later |
| **Go-live** | A + owner | Phase 9 | Billing approval, L7 | Later |

**Lead alerts at launch need no new code.** Phase 4 already emails every new lead and site-visit request to the CMS's sales inbox (Settings → Lead routing → inbox email; `mail/handlers.py`). At go-live: set **Settings → Lead routing → Shared sales inbox** to `sales@empirebuildcon.com` and add the production Resend key. This is on the go-live checklist.

## Decision numbers

D-050 is this launch order. L1 proposes D-051 if it changes how tests run; L2 to L7 take the next free numbers.
