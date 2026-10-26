# How work is done from Phase 5: developer agent, manager and owner

From Phase 5 a **developer agent** (Antigravity on the owner's computer, or any other AI or human developer) writes the code. **Claude** is the manager and tester. The **owner** approves and merges. This page is the process all three follow ([D-037](../DECISIONS.md)). If anything here conflicts with a task doc, the task doc wins for that task; if it conflicts with [`AGENTS.md`](../../AGENTS.md) or the security and honesty rules, those win.

## 1. Roles

| Who | Does | Never does |
|---|---|---|
| **Owner** | Starts each task by giving the developer its prompt; opens or approves the pull request; merges with **Squash and merge**; does every account, password and terms step. | — |
| **Developer agent** | Builds one task on one branch, with tests and handbook updates; runs the checks; pushes the branch; writes a report; fixes review findings on the same branch. | Pushes to `main`, merges, force-pushes `main`, works on two tasks at once, changes scope without saying so, types passwords or accepts terms. |
| **Manager (Claude)** | Writes the task docs and prompts; reviews every pushed branch from the owner's folder; runs the full check list in its own workspace; has an independent reviewer read the code; writes the review; tells the owner whether to merge; keeps the tracker, decisions log and handbook in order. | Has GitHub access (D-029); merges; commits on `main`. |

## 2. The cycle for one task

```
 manager            owner              developer agent             GitHub
 ───────            ─────              ───────────────             ──────
 task doc  ───────▶ gives prompt ────▶ 1 sync main, branch
                                       2 environment check
                                       3 read, plan, build, test
                                       4 checks, self-review
                                       5 commit, push  ─────────────▶ branch
                    opens PR  ──────────────────────────────────────▶ PR + CI
                                       6 report in docs/agent-reports/
 7 review  ◀─────── "5.1 ready"
   (fetch, checks, independent review)
   review file  ──▶ verdict
   fixes? ────────▶ gives fix prompt ─▶ 8 fix on the same branch, push, report
 9 "merge" ───────▶ Squash and merge
                    git pull ─────────────────────────────────────── main
 10 check merged == reviewed; next task doc
```

### Step by step

1. **Start from the latest `main`.**
   ```
   git switch main
   git pull
   git switch -c feat/<task-branch>
   ```
   The branch name is in the task doc (for example `feat/p5-1-public-api`).
2. **Environment check.** Follow [SETUP.md](../SETUP.md). Confirm Node, pnpm, uv, PostgreSQL and the Playwright browser work. If something is missing, **stop and tell the owner exactly what to install and why**; don't install system software on your own. Installing project dependencies with `pnpm install` and `uv sync` is fine.
3. **Read, plan, build.**
   - Read the task doc, then every file and handbook section it lists under "Read first".
   - Write a short plan at the top of your report file (step 6) before coding, so the manager can see your approach.
   - Build in small steps. Write the test with (or before) the code. Keep to the task's scope; put anything else in the report as a suggestion.
4. **Checks and self-review.** Run the full list in §4. Read your own diff (`git diff main...HEAD`) against the task's acceptance list and §5 before you push.
5. **Commit and push.**
   - Conventional Commits, usually one to three commits (`feat(api): …`, `feat(web): …`, `docs(handbook): …`), each ending with a `Co-Authored-By:` line naming the agent.
   - Run the secret scan on what you commit (`gitleaks protect --staged`, if installed; CI runs it anyway).
   - `git push -u origin feat/<task-branch>`. Never push `main`.
   - Pull request: if the GitHub CLI (`gh`) is installed and signed in, open it as a **draft** with the text from your report. Otherwise write the PR title and text into your report; the owner opens the PR.
6. **Report.** Write `docs/agent-reports/<task-id>.md` with the template in §6. `docs/` is private and never committed.
7. **Manager review.** The owner tells Claude "<task-id> ready". Claude fetches the branch from the owner's folder, runs every check, has an independent reviewer read the code and writes `docs/reviews/<task-id>-review-<n>.md` with a verdict.
8. **Fixes.** If the verdict asks for changes, the owner gives the developer the fix prompt from `docs/agent-prompts/`. Fix on the **same branch**, add commits (no force-push needed), push, and add a "Round <n>" section to your report saying what changed for each finding.
9. **Merge.** When the verdict is **Merge** and CI is green, the owner uses **Squash and merge** with the title Claude gives, then runs `git switch main` and `git pull`.
10. **After the merge.** Claude checks that the merged code is identical to what it reviewed, updates the tracker and the handbook status, and prepares the next task.

## 3. Rules that matter most

- Everything in [`AGENTS.md`](../../AGENTS.md): secrets, honest content, consent, tagged code (`DO NOT CHANGE`, `COMPLIANCE` only with the owner's approval), facts checked before relying on them.
- **Scope:** one task, one branch, one PR. Don't fix unrelated things in the same branch; list them in the report.
- **Contract:** the design contract is [`api/openapi-v1.yaml`](../api/openapi-v1.yaml). Keep its paths, operationIds and permissions. Every addition or deviation is listed in the report and in the task's decision record. Regenerate the client with `pnpm api:openapi && pnpm api:client` and commit both generated files; never edit them by hand.
- **Migrations:** add a new numbered migration; never edit one that is merged. Every migration has a working downgrade.
- **Tests are not optional.** New behaviour has tests; a bug fix has a test that fails without it. Never delete, skip or weaken an existing test to get green; if a test is wrong, say why in the report.
- **Dependencies:** add one only when needed. Check the current version and its date on the official registry, pin it, and give the reason in the report.
- **Browser suite budget:** a full `pnpm e2e` run signs in 6 times; the API allows 10 sign-ins per network in 15 minutes. Leave 15 minutes between full runs and add no sign-ins unless the task allows it. Public lead submissions are limited too (5 per 10 minutes per network).
- **Handbook:** update the page that describes what you changed, in the same branch. Decisions go in [`DECISIONS.md`](../DECISIONS.md) as the next free `D-0xx`, marked "(Proposed)"; the manager changes it to "Accepted" at review.
- **Comments:** follow [CODE_STYLE.md](../CODE_STYLE.md). Explain *why*, and tag regulated or security-sensitive code.
- **When unsure:** stop and write the question in your report rather than guessing on anything about money, RERA, consent, personal data or security.

## 4. Checks before every push (the same as CI)

The commands are in [SETUP.md § Checks](../SETUP.md#checks-the-same-as-ci). In short:

```
pnpm format:check
pnpm -r lint
pnpm -r typecheck
pnpm --filter @empire/ui test
pnpm --filter @empire/web test
pnpm --filter @empire/web build

cd apps/api
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest -q
cd ../..

pnpm api:openapi
pnpm api:client
git diff --exit-code -- packages/api-client

pnpm e2e
```

Also, when the task adds a migration: upgrade, downgrade and upgrade again on an empty database, then `uv run alembic check`. Report any check you couldn't run locally and why; CI is the final gate, but a red CI means the task isn't done.

**On Windows:** run these in PowerShell or the VS Code terminal from the repository folder. Use `cd apps\api` and `cd ..\..`; everything else is the same.

## 5. What the manager checks at review

- The task's acceptance list, item by item.
- Every check in §4, run again in a clean workspace, plus the migration cycle and a contract comparison.
- An independent code review (a reviewer that didn't write the code) for security, correctness, honesty and compliance rules, accessibility and test quality.
- Screenshots at desktop width and 390 px for anything visible.
- Handbook and decision updates, comments, and the report.

The review file lists findings as **Must fix** (blocks the merge), **Should fix** (fix in this branch unless the review says it can wait) and **Note** (no change needed), each with file, line, what is wrong and how to see it. The verdict is **Merge**, **Fix and re-review**, or **Stop** (the approach needs to change; the manager explains).

## 6. Report template (`docs/agent-reports/<task-id>.md`)

```markdown
# <task-id> · <task title> · report

## Plan (written before coding)
- …

## What I built
- …

## Acceptance list
- [x] item 1 — where it is and the test that proves it
- [ ] item n — not done, because …

## Checks
| Check | Result |
|---|---|
| format, lint, typecheck | pass |
| UI and web unit tests | N pass |
| API: ruff, format, mypy | pass |
| API: pytest | N pass (M new) |
| migration cycle + alembic check | pass / not applicable |
| contract regenerated, no diff | pass |
| web build | pass |
| e2e | N pass (sign-ins used: 6) |

## Contract changes
- Additions: …
- Deviations: …

## Decisions (D-0xx, Proposed)
- …

## Dependencies added
- name version (registry, date checked) — why

## Questions for the manager or owner
- …

## Not done / follow-ups
- …

## Pull request
Branch: `feat/…` · PR: <link, or "owner to open">
Title: …
Text: …

## Round 2 (after review 1)
- Finding 1: what changed, test
```

## 7. Prompts

The manager writes a ready-to-paste prompt for each task and each fix round in `docs/agent-prompts/` on the owner's computer. The owner pastes it into the developer agent. The developer treats the task doc in the repository as the source of truth; the prompt only points to it.
