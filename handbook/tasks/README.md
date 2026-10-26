# Task docs

Each task a developer works on is one file here, written by the manager (Claude) before the work starts. The process around it is [../agents/WORKFLOW.md](../agents/WORKFLOW.md).

## Format of a task doc

1. **Header:** task id, title, branch name, depends on, status.
2. **Goal:** what the owner gets when it's done, in plain words.
3. **Read first:** the handbook sections, decisions, contract parts, design boards and code the developer must read before coding.
4. **Scope:** numbered, concrete items. What is out of scope is listed too.
5. **Rules for this task:** anything beyond the standing rules (permissions, honesty, performance, sign-in budget).
6. **Tests required:** what must be proven, by which kind of test.
7. **Acceptance list:** the checklist the manager reviews against. The developer copies it into the report and ticks it.
8. **Handbook and decisions:** which pages to update; the decision number to propose.

## Status

| Phase | Plan | Tasks |
|---|---|---|
| 5 · Public website | [phase-5/PLAN.md](phase-5/PLAN.md) | 5.1 ready; 5.2–5.7 written one at a time, after the previous task is merged |

A task doc is not edited after its work starts, except to fix a mistake (noted at the bottom with the date). Changes of scope go in a new task.
