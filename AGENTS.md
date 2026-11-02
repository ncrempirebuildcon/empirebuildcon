# Rules for AI coding agents

This file is for AI assistants (Claude Code and others) working in this repository. Human contributors follow the same rules in [`handbook/`](handbook/README.md).

## Before you change anything

1. Read [`handbook/README.md`](handbook/README.md), [`handbook/CONTRIBUTING.md`](handbook/CONTRIBUTING.md) and [`handbook/CODE_STYLE.md`](handbook/CODE_STYLE.md).
2. Before touching a module, read the decisions it cites ([`handbook/DECISIONS.md`](handbook/DECISIONS.md)) and the matching section of [`handbook/ARCHITECTURE.md`](handbook/ARCHITECTURE.md).
3. Pull the latest `main` and work on a branch (`feat/…`, `fix/…`). Never commit on `main`.

## Hard rules

- **Secrets:** never print, store, commit or ask for passwords, API keys, tokens or connection strings. Only `.env.example` with names is committed. If a secret appears, don't repeat it; tell the owner to rotate it.
- **Git:**
  - Never push to `main`, never merge your own pull request, and never force-push a branch you did not create.
  - Claude has no GitHub access (owner's decision, 22 Oct 2026, D-029). From Phase 5, Claude is the **manager and tester**: it writes the task docs, reviews branches and recommends whether to merge (D-037). From task 5.3 Claude also builds the Track A tasks on its own branches, which the owner pushes (D-040).
  - A **developer agent** (for example Antigravity on the owner's computer) works on its own `feat/…` branch and may push that branch from the owner's computer with `git push -u origin <branch>`. Only the owner merges.
  - Follow [`handbook/agents/WORKFLOW.md`](handbook/agents/WORKFLOW.md) for every task: one task doc, one branch, one pull request, a written report, then the manager's review.
- **Accounts:** never sign in, type passwords or accept terms for the owner. Ask them to do it.
- **Tagged code:** code marked `DO NOT CHANGE:` or `COMPLIANCE:` changes only with the owner's approval. Explain the change and the risk in the pull request.
- **Honest content:**
  - Show the UP-RERA number, QR code and up-rera.in on every project, property or ad view.
  - Carpet area comes first, in sq ft and sq m.
  - Prices carry the note "excludes GST, stamp duty and registration".
  - No fake urgency.
  - Don't invent facts. Use `[placeholders]`, and flag sample data `is_sample`.
- **Consent:** required and optional consent are separate and never pre-ticked. The consent text version is stored with the lead. Leads are never hard-deleted.
- **Facts:** check versions, prices and plan limits before relying on them, and say what you checked.
- `docs/` is the owner's private folder. It is not in git, so don't recreate it or copy it into the repo.

## Where your task is

- The task you are working on is a file in [`handbook/tasks/`](handbook/tasks/README.md), for example `handbook/tasks/phase-5/5.1-public-api.md`. Do exactly that task; anything else goes in your report as a suggestion.
- Write your report to `docs/agent-reports/<task-id>.md` (private, not committed) using the template in the workflow doc. Read the manager's review in `docs/reviews/<task-id>-review-<n>.md`.
- Design boards (HTML) for the public site are in `docs/design-boards/` on the owner's computer.

## When you finish a change

- Update the handbook page that describes the behaviour you changed, in the same commit or pull request.
- Comment complex logic with the tags in CODE_STYLE §2 (`WHY`, `INVARIANT`, `DO NOT CHANGE`, `COMPLIANCE`, `SECURITY`, `PERF`, `TODO(phase-N)`).
- Run the checks listed in [`handbook/SETUP.md`](handbook/SETUP.md) and [`handbook/CONTRIBUTING.md`](handbook/CONTRIBUTING.md) §6.
- Add a `Co-Authored-By:` line naming the assistant to your commit messages.
