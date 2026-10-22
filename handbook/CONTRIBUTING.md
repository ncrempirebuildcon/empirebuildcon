# Contributing: git, push/pull and review rules

Every contributor follows these rules. That includes the owner, outside developers and AI assistants such as Claude. The aim is simple: `main` always works, anyone can see why each change was made, and nobody overwrites someone else's work.

## 1. The short version

1. Pull before you start: `git switch main && git pull --ff-only`.
2. Make a branch for one topic: `git switch -c feat/leads-csv-export`.
3. Make small commits with clear messages (§4).
4. Run the checks locally, then push **your branch**: `git push -u origin feat/leads-csv-export`.
5. Open a pull request (PR) into `main` and fill in the template.
6. Get one approval. Get the owner's approval for the items in §7. CI must be green.
7. **Squash and merge**, then delete the branch.

Never push to `main` directly. Never force-push a branch someone else is working on.

## 2. One-time setup on your computer

```bash
git config --global pull.ff only           # pull never makes surprise merge commits
git config --global fetch.prune true       # forget branches deleted on GitHub
git config --global rebase.autoStash true
git config --global init.defaultBranch main
# Windows only:
git config --global core.autocrlf false    # .gitattributes controls line endings (LF)
git config --global core.longpaths true
```

Use your own GitHub account. Ask the owner to add you to the repository. Never share accounts or tokens.

## 3. Branches

| Branch | Purpose | Who pushes |
|---|---|---|
| `main` | Always deployable. Every merge deploys to staging (production is promoted by the owner from Phase 9). | Nobody directly. Only through merged PRs. |
| `feat/<area>-<topic>` | New feature, e.g. `feat/cms-media-reorder` | The author |
| `fix/<area>-<topic>` | Bug fix, e.g. `fix/web-emi-rounding` | The author |
| `chore/…`, `refactor/…`, `test/…`, `docs/…` | Upkeep, restructuring without behaviour change, tests only, handbook only | The author |
| `hotfix/<topic>` | Urgent production fix, branched from `main`, same PR rules, fast review | The author |

Rules:
- One topic per branch. Keep branches short-lived: aim to merge within a week, and split big work into several PRs.
- Use lowercase and hyphens. `<area>` is one of: `web`, `cms`, `api`, `worker`, `db`, `ui`, `infra`, `qa`, `handbook`, `brand`.
- Someone else's branch is **theirs**. To help, branch off it and open a PR into it, or agree with them first.

## 4. Commits

Format: [Conventional Commits](https://www.conventionalcommits.org/).

```
type(area): short summary in the imperative, max 72 characters

Why the change was needed and what it does, wrapped at 72 characters.
Mention the decision or issue it follows, e.g. "Follows D-016".

Refs: #123
```

- **Types:** `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `build`, `ci`, `revert`.
- **Examples:** `feat(cms): reorder project photos by drag and drop` · `fix(api): reject PNG uploads with an SVG payload`.
- Each commit should build and pass the tests. Don't mix unrelated changes, and don't commit commented-out code.
- A breaking change gets `!` after the type (`feat(api)!: …`) and a `BREAKING CHANGE:` line in the body.
- AI-assisted commits add a `Co-Authored-By:` line naming the assistant.

## 5. Keeping up to date (pull)

- **On `main`:** `git pull --ff-only`. If that fails, you have local commits on `main` by mistake. Move them to a branch: `git switch -c fix/my-work`, then `git switch main && git reset --hard origin/main`.
- **On your own branch:** rebase onto the latest `main` before you open the PR and whenever `main` moves under you:
  ```bash
  git fetch origin
  git rebase origin/main
  # fix conflicts, then: git add <files> && git rebase --continue
  git push --force-with-lease
  ```
- `--force-with-lease` is allowed **only on your own feature branch**. Never use plain `--force`, and never force on `main`.
- **On a shared branch** (two people on the same branch): use `git pull --rebase` and don't rewrite commits that are already pushed.
- **Conflicts:** resolve them on your branch, then run the tests again. If you don't understand the other change, ask its author (`git log -p <file>` shows who). Never "fix" a conflict by deleting the other person's code.

## 6. Before you push

Run the same checks CI runs. The exact commands are in [SETUP.md § Checks](SETUP.md#checks-the-same-as-ci). They cover:

- formatting and lint (Prettier and ESLint for the web, Ruff for Python);
- type-check (`tsc`, mypy);
- tests (pytest for the API; Playwright and axe for browser journeys);
- database migrations from an empty database;
- the OpenAPI contract and generated client;
- build.

Also check:
- no secrets, `.env` files, personal data or large binaries (more than 5 MB) in the diff;
- any handbook page that describes what you changed is updated in the same PR;
- comments follow [CODE_STYLE.md](CODE_STYLE.md), especially around anything complex or regulated.

## 7. Pull requests and review

- Open the PR early as a **draft** if you want feedback. Mark it ready when CI is green.
- Fill in the template: what and why, how you tested it, screenshots for any UI change (mobile and desktop), migration notes, risks, and the decisions it follows.
- Keep PRs small: under about 400 changed lines, excluding generated files and lockfiles.
- **One approval** from someone other than the author is needed to merge. Authors never approve or merge their own PR.
- Reviewers check:
  - correctness and tests;
  - permissions checked in the API;
  - the honesty rules ([handbook README](README.md#rules-that-never-bend));
  - accessibility;
  - comments on complex code;
  - handbook updates.
- Resolve every conversation before merging. Use **Squash and merge**, with the PR title as the commit message.

### Owner approval

These changes need the owner's approval on the PR, in addition to the normal review:

- auth, sessions, two-factor, roles and the permission matrix;
- lead capture, consent text or wording, data retention and erasure;
- anything that shows or hides the UP-RERA number or QR code, prices or legal and disclaimer text;
- database migrations that drop or rewrite data;
- hosting, DNS, environment variables, paid plans and new third-party services;
- anything marked `DO NOT CHANGE` or `COMPLIANCE` in the code ([CODE_STYLE.md](CODE_STYLE.md)).

## 8. Database migrations

- Use Alembic. Put a migration in the PR that needs it, and don't edit a migration that is already merged; add a new one instead.
- Every migration has a working downgrade, or a comment explaining why it can't, plus owner approval.
- Make schema changes in two steps when data is involved: first add and backfill, then remove in a later PR. That way a deploy never breaks the running version.

## 9. Generated files

Some files are generated, such as the typed API client from the OpenAPI spec ([D-020](DECISIONS.md)). They start with a header saying how to regenerate them. Never hand-edit them. CI fails if they are stale.

## 10. Releases

- Every merge to `main` deploys to **staging** (from Phase 9).
- The owner promotes to **production** after checking staging, and tags it `vYYYY.MM.DD` (add `.N` for a second release the same day).
- Rollback means redeploying the previous tag. `handbook/RUNBOOK.md` (written in Phase 9) will have the steps.

## 11. AI assistants (Claude and others)

AI assistants follow every rule above, plus these:

- Always pull the latest `main` before starting, and work on a branch.
- **Pushing:** Claude has no GitHub access (D-029).
  - Claude builds and tests in its own workspace, then commits on a feature branch in the owner's working copy.
  - The owner pushes the branch, opens the PR and merges.
  - Other AI assistants work the same way, unless the owner gives them their own access.
- **Before new work,** the owner fetches from GitHub (GitHub Desktop: **Fetch origin**), so Claude starts from the latest `main`.
- Claude never commits on `main`. The only exception is the one-time bootstrap commit that created it (handbook and brand files, no code), so that pull requests have a base.
- Never type, store or ask for passwords or tokens. The owner does account and sign-in steps.
- Leave the handbook and the code comments good enough that the next person, human or AI, can continue without asking.

The same rules for AI agents are in [`../AGENTS.md`](../AGENTS.md).

## 12. Repository settings on GitHub (owner)

The owner sets these once, after the first push. They turn the rules above into settings that GitHub enforces.

**Branch protection for `main`** (Settings → Branches → Add rule, or Settings → Rules → New ruleset):
- Require a pull request before merging, with 1 approval. Dismiss stale approvals when new commits are pushed.
- Require these status checks to pass: `secrets`, `api`, `web`, `contract`, `e2e`. Require the branch to be up to date.
- Require conversation resolution.
- Block force pushes and deletions.
- Allow only **squash merging** (Settings → General → Pull requests), and turn on "Automatically delete head branches".

**GitHub plan (checked 22 Oct 2026, D-028):**
- On **GitHub Free**, protected branches and rulesets work only on *public* repositories. On a *private* repository they need GitHub Pro (personal account) or GitHub Team (organisation).
- The owner chose to stay on Free for now (22 Oct 2026). A paid plan needs management approval.
- Until then, GitHub enforces none of the protection settings above. Everyone follows the rules by hand, and the owner checks that CI is green before merging. The merge settings (squash only, delete head branches) do work on Free.
- GitHub Free includes 2,000 Actions minutes a month for private repositories. After the first few CI runs, check the real use under Settings → Billing and plans. Concurrent runs on the same branch cancel each other (`concurrency` in `ci.yml`), which saves minutes.
