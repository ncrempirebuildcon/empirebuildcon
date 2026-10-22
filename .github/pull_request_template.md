## What and why
<!-- One or two sentences. Link the decision (D-0xx) or issue this follows. -->

## How I tested it
<!-- Commands run, test cases added, manual checks. UI changes: screenshots on mobile (390 px) and desktop. -->

## Checklist
- [ ] Branch is up to date with `main` (rebased) and CI is green
- [ ] Tests added or updated (bug fixes have a failing-before test)
- [ ] No secrets, `.env` files, personal data or files over 5 MB in the diff
- [ ] Complex or regulated code is commented with the tags in `handbook/CODE_STYLE.md` §2
- [ ] Handbook pages that describe this behaviour are updated
- [ ] Honesty rules kept: RERA number + QR on project/property/ad views, carpet area in sq ft and sq m, price exclusions note, no fake urgency, no invented data
- [ ] Accessibility: labels, focus ring, keyboard use, 44 px touch targets, colour not the only signal
- [ ] Database migration included (if needed), with a working downgrade or a written reason
- [ ] Needs **owner approval** (auth/permissions, consent or legal text, RERA/price display, data-dropping migration, hosting/DNS/env, `DO NOT CHANGE`/`COMPLIANCE` code)? If yes, tag the owner.

## Risks and rollback
<!-- What could go wrong, and how to undo it. -->
