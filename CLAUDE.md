# Purchase Management System (procure-to-pay) — campus hiring demo

## Source of truth — read before changing anything
- `SPEC.md` (revision 2): requirements and business rules
- `docs/DESIGN.md`: folder structure, ER diagram, state machines, API endpoints + role access
- `DECISIONS.md`: every design decision with its reason (D-01 …). Add an entry for each new
  significant decision; never silently contradict an existing one.

## Resolved with the owner (do not re-ask)
- DEPT_HEAD-raised PRs skip the dept-head level and go straight to FINANCE, on submit and resubmit.
- MISMATCH invoices: *rematch* (re-runs the check, no line edits) or *reject* (reason, terminal).
  Correction = reject + enter a fresh invoice; REJECTED invoices don't block reuse of the number.
- Only MATCHED (and later PAID/PARTIALLY_PAID) invoices count toward `qty_invoiced`.
- Cancelling a PO returns its PR to APPROVED; short-close (SHORT_CLOSED) is in v1; invoices are
  allowed on SHORT_CLOSED POs; an unresolved MISMATCH invoice blocks PO auto-close.
- Budget: final-approval month, PRs in APPROVED/PO_CREATED.
- REQUESTER / DEPT_HEAD have scoped read-only visibility; ADMIN = master data + read-only.
- Out-of-scope records return 404 (role with no access at all → 403).

- DRAFT PRs are visible only to their author (D-45).
- Expired quotations don't count for rule 6 ("< 2 quotes", "lowest"); shown but flagged (D-50).

## Build status
- Phase 1 (design) done. Phase 2 (models, auth, scoping, seed) done and committed.
- Phase 3 (service layer + pytest suite) done: every SPEC rule in `app/services/`; the seed is
  built through the services.
- Phase 4 (REST API, 52 operations under `/api`, conventions in D-54) done.
- Phase 5 (Next.js 14 frontend in `frontend/`, conventions in D-56) done.
- Phase 6 (review, fresh-clone test, offline/demo safety, E2E, README, cheat sheet) done.
  See D-57, D-58. README.md is written for reviewers; docs/DEMO_CHEATSHEET.md for the demo.

## Commands
- `./dev.sh` (repo root) — backend on :8000 + frontend on :3000; `--reset` restores the demo
  data (also works while running). `PMS_BACKEND_PORT` / `PMS_FRONTEND_PORT` move the ports.
- `cd frontend && npm run e2e` — Playwright, isolated DB + ports (:8011/:3011), needs Chrome;
  `npm run e2e:screenshots` also regenerates docs/screenshots.

From `backend/`:
- `./run.sh` — venv + deps, seeds on first run, API on http://localhost:8000 (docs at `/docs`)
- `./run.sh --reset` / `./reset_db.sh` — drop all tables, recreate, reseed (safe while running)
- `.venv/bin/python -m pytest` — full suite (fresh SQLite file per test, ~10 s)
- Demo users: `<role>@example.com` style, e.g. `requester.it@`, `head.ops@`, `finance@`; password `demo123`

## Conventions
- Router → service → model. Business rules only in `app/services/`; routers stay thin.
- Status changes go through a transition table and write an AuditLog row in the same transaction.
- Money/quantities: `Decimal` only; columns are `Money`/`Quantity` (scaled integers, D-38).
- Time: always `app.core.clock.now()/today()` (naive IST), never `datetime.now()`.
- Reads: use `app.services.access` (`scoped_select`, `get_visible_or_404`,
  `audit_visible_filter`). Writes: `require_roles(...)` in `app.core.deps`; never include ADMIN
  on a transactional endpoint.
- Errors: raise `app.core.errors` types (409 transition/status guard, 422 rule or bad input,
  403 role, 404 scope). A failed three-way match is a MISMATCH result, not an error (D-51).
- Routers: `user: Allow(roles)` → `access.get_visible_or_404` → service → `db.commit()` →
  `views.*` presenter. GET role lists come from `access.readers(Model)`.
- Money math: always `line_amount(qty, price)` (rounded to the paisa, D-53), never raw `*`.
- Service actions: `@atomic` (SAVEPOINT), take `actor` first, check role with `ensure_role`,
  status with `state_machine.check/require_status`, and never commit — the caller does (D-46).
- Tests: use the `w` (World) fixture to reach any state via services; the clock is frozen at
  `tests.conftest.NOW`; move it with `w.later(...)` or `clock.freeze(...)`.
- The seed must pass `app/seed/verify.py`; extend the checks when adding invariants.
- Frontend: buttons come ONLY from the API's `actions`; never add permission/business logic
  in `frontend/`. Money is formatted from decimal strings (`lib/format.ts`), never floats.
  Any arithmetic the UI does for previews goes through `lib/decimal.ts` (D-57).
  Check with `npx tsc --noEmit`, `npx next lint`, `npm run build` (from `frontend/`; builds into
  `.next-build/`, so it's safe while the dev server runs).
