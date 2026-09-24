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

## Build status
- Phase 1 (design) done. Phase 2 (backend foundation) done: models, enums, constraints,
  numbering, JWT auth, role dependency, visibility scoping, seed. No workflow services or
  workflow endpoints yet — only `/api/health` and `/api/auth/*`.

## Commands (from `backend/`)
- `./run.sh` — venv + deps, seeds on first run, API on http://localhost:8000 (docs at `/docs`)
- `./run.sh --reset` / `./reset_db.sh` — drop all tables, recreate, reseed (safe while running)
- Demo users: `<role>@example.com` style, e.g. `requester.it@`, `head.ops@`, `finance@`; password `demo123`

## Conventions
- Router → service → model. Business rules only in `app/services/`; routers stay thin.
- Status changes go through a transition table and write an AuditLog row in the same transaction.
- Money/quantities: `Decimal` only; columns are `Money`/`Quantity` (scaled integers, D-38).
- Time: always `app.core.clock.now()/today()` (naive IST), never `datetime.now()`.
- Reads: use `app.services.access` (`scoped_select`, `get_visible_or_404`,
  `audit_visible_filter`). Writes: `require_roles(...)` in `app.core.deps`; never include ADMIN
  on a transactional endpoint.
- Errors: raise `app.core.errors` types (409 transition, 422 rule, 403 role, 404 scope).
- The seed must pass `app/seed/verify.py`; extend the checks when adding invariants.
