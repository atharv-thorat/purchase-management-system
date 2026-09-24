# Decision Log

Each entry records a decision and why it was made. **Source** says where it came from:
*Owner* = explicit answer from the project owner; *Default accepted* = design-pass proposal
the owner accepted; *Design* = technical choice made while designing.
Q-numbers refer to the open questions in the first design pass (2026-09-24).

---

## Workflow and business rules

### D-01 — PRs raised by a DEPT_HEAD escalate straight to FINANCE
- **Source:** Owner (Q1) · 2026-09-24
- **Decision:** DEPT_HEADs may raise PRs. On submit (and resubmit) such PRs skip the dept-head
  level and go to PENDING_FINANCE, whatever the amount. FINANCE is the only approver.
- **Why:** The ban on self-approval means no one in the department could approve a dept head's
  PR. Blocking dept heads from buying would be unrealistic, so the next level up approves
  instead.

### D-02 — Resubmitting a rejected PR restarts the full approval chain
- **Source:** Default accepted (Q2)
- **Decision:** A resubmitted PR goes back to the entry state for its requester
  (PENDING_DEPT_HEAD, or PENDING_FINANCE under D-01), even if an earlier level had approved it.
- **Why:** The requester may have changed lines and amounts while editing, so earlier approvals
  no longer apply to what is being submitted.

### D-03 — MISMATCH invoices can be rematched or rejected; rejected numbers can be reused
- **Source:** Owner (Q3)
- **Decision:** From MISMATCH, ACCOUNTS can *rematch* (→ PENDING_MATCH → MATCHED/MISMATCH,
  re-evaluated against current data, with no line edits) or *reject* (→ REJECTED, terminal,
  reason required). REJECTED invoices are left out of the duplicate supplier-invoice-number
  check.
- **Why:** In the original spec MISMATCH was a dead end. Rematch covers goods that arrive
  after the invoice. Reject covers a genuinely wrong invoice. Excluding REJECTED from the
  duplicate check lets the supplier's corrected invoice be entered under the same number.

### D-04 — Only MATCHED invoices count toward `qty_invoiced`
- **Source:** Owner (Q4)
- **Why:** A mismatched invoice isn't accepted yet. If it used up invoiceable quantity, a
  correct invoice for the same goods would then fail the match.

### D-05 — Budget check definition
- **Source:** Owner (Q11)
- **Decision:** Approved total this month = Σ over the department's PRs in APPROVED or
  PO_CREATED whose `final_approved_at` falls in the current calendar month. Each is valued at
  its non-cancelled PO total if one exists, else its `estimated_total`. The PR under approval
  is excluded, then its `estimated_total` is added and the result compared with
  `monthly_budget`.
- **Why:** Final approval is when the money is committed. The PO total is the real committed
  figure once it exists, and the estimate is the best figure before that.

### D-06 — Cancelling a PO returns the PR to APPROVED
- **Source:** Owner (Q7)
- **Decision:** PO cancel → PR goes from PO_CREATED back to APPROVED and the quotation selection
  is cleared. The cancelled PO is kept. "One PR → one PO" applies to non-cancelled POs only,
  enforced by a partial unique index.
- **Why:** An approved need doesn't go away because a supplier fell through. Purchase should be
  able to pick another quote without the PR being approved again.

### D-07 — Short-close for POs
- **Source:** Owner (Q9)
- **Decision:** PURCHASE can short-close a PARTIALLY_RECEIVED PO with a mandatory reason →
  SHORT_CLOSED. No further GRNs are allowed. Invoicing and payment of accepted quantities
  continue. It auto-closes to CLOSED once all accepted quantity is invoiced and all live
  invoices are PAID.
- **Why:** If a supplier never delivers the balance, the PO would otherwise stay open forever
  and never reach CLOSED.

### D-12 — Finance threshold is read at dept-head approval time
- **Source:** Default accepted (Q12)
- **Why:** That is the moment routing is decided. Freezing it at submission would be a surprise
  if ADMIN changed the setting while the PR was waiting.

### D-13 — PRs: delete DRAFT only; no CANCELLED state
- **Source:** Default accepted (Q6)
- **Why:** Keeps the PR state machine small. A REJECTED PR that is never resubmitted simply
  stays REJECTED.

### D-14 — Expired quotations cannot be selected
- **Source:** Default accepted (Q13)
- **Why:** The supplier is no longer bound to those prices. The PO would snapshot a price that
  may not be honoured.

### D-15 — Quotation total is computed; quantities equal the PR's
- **Source:** Default accepted (Q14)
- **Why:** Quotes have to be comparable line by line. Computed totals can't disagree with their
  lines.

### D-16 — One quotation per supplier per PR
- **Source:** Default accepted (Q15)
- **Why:** Stops the "≥2 quotations" rule from being met with two quotes from the same supplier.
  A revised quote is an edit, not a second quote.

### D-17 — Any GRN blocks PO cancellation
- **Source:** Default accepted (Q8)
- **Decision:** Even a GRN where everything was rejected counts as "received".
- **Why:** Goods physically arrived and a document exists. Cancelling would orphan that
  receipt record.

### D-18 — PO receipt status is driven by accepted quantity
- **Source:** Default accepted (Q10)
- **Decision:** Σaccepted = 0 → ISSUED; partial → PARTIALLY_RECEIVED; every line complete →
  FULLY_RECEIVED. Recomputed after every GRN.
- **Why:** Rejected goods are going back to the supplier, so they don't fulfil the order.

### D-20 — Invoice total is entered and checked against its lines
- **Source:** Default accepted (Q5)
- **Decision:** A difference between the entered total and Σ(qty × unit_price) is an extra
  MISMATCH reason.
- **Why:** The printed total is what the supplier is asking to be paid. Arithmetic errors on
  invoices are a real fraud and error route.

### D-21 — Price match is exact, to the paisa
- **Source:** Default accepted (Q17)
- **Why:** The PO price is a snapshot of an agreed price, so any tolerance would be arbitrary.
  All money is handled as `Decimal` to make exact comparison safe.

### D-25 — Invoices only against PARTIALLY_RECEIVED, FULLY_RECEIVED or SHORT_CLOSED POs
- **Source:** Default accepted (Q16), extended for D-07
- **Why:** An ISSUED PO has nothing accepted, so any invoice would mismatch. CANCELLED and
  CLOSED POs are finished. SHORT_CLOSED is included because goods already accepted still have
  to be billed and paid before the PO can close.

---

## Roles and access

### D-08 — Read visibility for requesters and dept heads
- **Source:** Owner (Q18)
- **Decision:** REQUESTERs get read-only access to the POs, GRNs, invoices and payments linked to
  their own PRs. DEPT_HEADs get the same for every PR in their department. Other role scopes
  are listed in SPEC.md.
- **Why:** Requesters need to see whether their goods have been ordered and received without
  asking Purchase or Stores. Dept heads need that view for their whole budget.

### D-09 — ADMIN is read-only for transactions
- **Source:** Owner (Q21)
- **Decision:** ADMIN manages master data and can read everything, but takes no transactional
  action (no approve, quote, receive, invoice or pay).
- **Why:** Segregation of duties. A super-user who can both configure and transact defeats the
  controls the system exists to enforce.

### D-10 — Only ADMIN creates suppliers
- **Source:** Default accepted (Q20)
- **Why:** Supplier onboarding is a control point. If Purchase could create suppliers
  themselves, they could quote from a fake supplier.

### D-19 — Only REQUESTER and DEPT_HEAD belong to departments and raise PRs
- **Source:** Default accepted (Q19), amended by D-01
- **Decision:** `user.department_id` is nullable and required only for REQUESTER and DEPT_HEAD.
- **Why:** FINANCE, PURCHASE, STORE, ACCOUNTS and ADMIN act across departments. Letting them
  raise PRs would create more self-approval edge cases.

### D-22 — One role per user
- **Source:** Default accepted (Q22)
- **Why:** Segregation of duties is easy to enforce and demo when a person can't hold two
  roles in the chain.

### D-23 — Users have `is_active`
- **Source:** Default accepted (Q23)
- **Why:** People leave, but their approvals and receipts must stay attributable. Deactivated
  users can't log in or act.

---

## Data, seed and project

### D-11 — Project lives in `~/purchase-management/` as a git repo
- **Source:** Owner (Q25)
- **Why:** SPEC.md was in the home directory. A dedicated repo keeps the project isolated and
  versioned.

### D-24 — Demo users
- **Source:** Default accepted (Q24)
- **Decision:** 9 users. REQUESTER and DEPT_HEAD in both IT and Operations, plus one each of
  FINANCE, PURCHASE, STORE, ACCOUNTS and ADMIN. HR has no users (it exists for the budget
  view).
- **Why:** This is the smallest set that shows cross-department scoping and D-01 escalation.

---

## Technical design

### D-26 — Business rules live only in the service layer
- **Source:** Design (required by SPEC)
- **Decision:** Router → service → model. Routers handle auth, parsing and serialisation only.
- **Why:** Rules can be unit-tested without HTTP, and there's one enforcement point.

### D-27 — Explicit transition tables and error mapping
- **Source:** Design
- **Decision:** Each entity has a `{(from_status, action): to_status}` table. Invalid
  transition → 409; rule violation → 422; role/scope violation → 403. Each carries an error
  code and a human-readable message.
- **Why:** The state machines can be read in one place and are testable exhaustively, and the
  frontend can show the backend's message directly.

### D-28 — One DB transaction per action, including audit rows
- **Source:** Design
- **Why:** A status change must never exist without its AuditLog entry, or the other way round.

### D-29 — Server-computed totals
- **Source:** Design
- **Decision:** PR, quotation and PO totals come from their lines. Client-sent totals are
  ignored. The exception is invoice total (D-20).
- **Why:** Totals can't disagree with their lines.

### D-30 — `Numeric` columns and `Decimal` everywhere for money and quantities
- **Source:** Design
- **Why:** Float rounding would break exact matching (D-21) and could produce false
  overpayment results.

### D-31 — Document numbers from a sequence table, assigned at creation
- **Source:** Design
- **Why:** Gives gap-free, readable numbers (PR-0001) inside the same transaction. The number
  exists as soon as the draft does, so it can be referred to at once.

### D-32 — Partial unique indexes back the uniqueness rules
- **Source:** Design
- **Decision:** `invoice(supplier_id, supplier_invoice_number) WHERE status <> 'REJECTED'`,
  `purchase_order(pr_id) WHERE status <> 'CANCELLED'`, `quotation(pr_id, supplier_id)`.
- **Why:** The database is a second line of defence behind the service checks. SQLite
  supports partial indexes.

### D-33 — Quotation selection and PO creation are one atomic action
- **Source:** Design (SPEC lists "select-and-create-PO action")
- **Why:** This removes the in-between state "selected but no PO", which would otherwise need
  its own rules.

### D-34 — When PO auto-close is evaluated
- **Source:** Design (follows from D-03 and D-07)
- **Decision:** After a payment is recorded, an invoice is rejected, or a PO is short-closed.
  Close condition: status FULLY_RECEIVED or SHORT_CLOSED, every line invoiced = accepted, and
  every non-REJECTED invoice PAID.
- **Why:** These are the only events that can make the condition true. An outstanding
  MISMATCH invoice deliberately blocks closure.

### D-35 — PENDING_MATCH is transient but audited
- **Source:** Design
- **Why:** The match runs synchronously, so the invoice never rests in PENDING_MATCH. Logging
  both hops keeps the timeline true to the spec's state machine.

### D-36 — Over-budget flag stored on ApprovalLog
- **Source:** Design (SPEC rule 4: "approval still allowed, but logged")
- **Why:** Budget figures change over time, so the warning the approver actually saw must be
  kept as it was.

### D-37 — Out-of-scope records return 404, not 403
- **Source:** Design (follows from D-08)
- **Why:** Doesn't reveal whether another department's document exists.

### D-38 — Money and quantities stored as scaled integers (refines D-30)
- **Source:** Design (Phase 2)
- **Decision:** `Money` columns store paise and `Quantity` columns store thousandths, as
  integers. Python always sees `Decimal`. Assigning a float, or a value with too many decimal
  places, raises an error instead of rounding.
- **Why:** SQLite has no decimal type. `Numeric` there is a float underneath, so SQL-side
  sums and CHECK arithmetic would be inexact (0.1 + 0.2 ≠ 0.3). Scaled integers are exact
  everywhere, including inside the database.

### D-39 — Database constraints back the invariants (extends D-32)
- **Source:** Design (Phase 2)
- **Decision:** Enum columns carry CHECK constraints. `po_line` enforces
  0 ≤ qty_invoiced ≤ qty_accepted ≤ qty_ordered. `grn_line` enforces accepted + rejected =
  received. Rejections, cancellations and short-closes need a reason. `user.department_id` is
  set iff the role is REQUESTER or DEPT_HEAD. A partial unique index allows only one selected
  quotation per PR.
- **Why:** Services remain the enforcement point and give the readable errors. The database
  stops a bug or a stray script from storing a state the business rules forbid.

### D-40 — One clock, naive IST timestamps
- **Source:** Design (Phase 2), follows SPEC assumption "month = calendar month in IST"
- **Decision:** All timestamps come from `app/core/clock.py` and are stored as naive
  `Asia/Kolkata` datetimes. The zone comes from configuration, not from the host machine.
- **Why:** The budget month (D-05) is then a plain comparison and doesn't depend on the
  laptop's timezone. Tests and the seed pin the clock with `clock.freeze` / `frozen_at`.

### D-41 — Seed writes history directly and must pass an invariant check
- **Status:** Superseded in part by D-49 (the seed now calls the services). The invariant
  check and the current-month timeline still apply.
- **Source:** Design (Phase 2; workflow services not built yet)
- **Decision:** The seed builds each scenario step by step. Every status change gets its
  AuditLog row, and approvals get ApprovalLog rows. `seed/verify.py` then checks the SPEC
  invariants (totals, snapshots, cumulative quantities, status vs quantities and payments,
  audit chain continuity) and refuses to commit if any fail. Timestamps are placed relative to
  now and compressed into the current calendar month.
- **Why:** The demo data can't be produced by services that don't exist yet, but it must
  still be data those services could have produced. Keeping it in the current month means
  the budget figures and the over-budget warning on PR-0007 work whatever day the seed runs.
  Once services exist, the seed can be switched to call them and keep the same checks.

### D-42 — `requirements.txt` plus two scripts instead of `pyproject.toml`
- **Source:** Owner (Phase 2 instruction)
- **Decision:** `backend/requirements.txt`. `./run.sh` creates the venv, installs, seeds on
  first run and starts uvicorn. `./reset_db.sh` drops, recreates and reseeds.
- **Why:** Simplest setup for a live laptop demo. The reset works while the server is
  running, because it drops tables in the same file rather than deleting it.

### D-43 — Auth details
- **Source:** Design (Phase 2)
- **Decision:** JSON login returns an 8-hour HS256 JWT whose `sub` is the user id. Every
  request re-reads the user, so deactivation and role changes take effect at once. Emails are
  matched case-insensitively. `/auth/demo-users` works only when `PMS_DEMO_MODE` is on.
  Passwords are hashed with bcrypt.
- **Why:** Stateless tokens are enough for a demo. Re-reading the user closes the gap where
  a deactivated user keeps acting until the token expires (D-23).

### D-44 — Audit rows cover PR, PO and invoice; readable iff the entity is
- **Source:** Design (Phase 2)
- **Decision:** `AuditLog.entity_type` is PURCHASE_REQUEST, PURCHASE_ORDER or INVOICE, the
  three entities with status machines. A GRN is logged as `GRN_RECORDED` on its PO, and a
  payment as `PAYMENT_RECORDED` on its invoice, with the document number or amount in
  `details`. A caller can read an audit row exactly when they can read its entity.
- **Why:** Rule 15 covers status changes, and GRNs and payments are what change PO and invoice
  status. Tying audit visibility to entity visibility keeps timelines from leaking
  out-of-scope documents (D-37).

### D-45 — DRAFT PRs are visible only to their author
- **Source:** Owner (Phase 2 review) · 2026-09-24
- **Decision:** On top of every role's PR scope, a DRAFT is readable only by its requester.
  Dept heads, FINANCE, PURCHASE and ADMIN get 404 for someone else's draft, and its audit rows
  are hidden too. Once submitted, the PR follows the normal scopes.
- **Why:** A draft is unfinished work. Nobody else needs to act on it or report on it.

### D-46 — Each service action runs in a SAVEPOINT; the caller commits
- **Source:** Design (Phase 3), implements D-28
- **Decision:** Every public service action is wrapped in `@atomic` (`db.begin_nested()`). If
  it raises, every change it made is rolled back: status, audit rows, lines, document number.
  The session stays usable. Services never commit. A router commits once per request, and the
  seed commits once at the end. The engine takes over BEGIN from pysqlite so SAVEPOINT works.
- **Why:** An action is all-or-nothing even when one action calls another (select → create
  PO, payment → auto-close), and callers can still group actions into a bigger unit.

### D-47 — Write transactions take the SQLite lock up front
- **Source:** Design (Phase 3)
- **Decision:** Transactions start with `BEGIN IMMEDIATE`.
- **Why:** Rules such as "total paid ≤ invoice total" and "cumulative accepted ≤ ordered"
  read and then write. Serialising transactions means two requests can't both pass the check.
  Demo traffic is tiny, so the lost concurrency doesn't matter.

### D-48 — Input sanity rules added by the services
- **Source:** Design (Phase 3); accepted as-is by the owner (Phase 3 review).
- **Decision:** On top of the SPEC rules, the services refuse:
  - PRs: `required_by` in the past (on create, edit and submit); the same item on two lines;
    quantity or estimated price ≤ 0.
  - Quotations: quote date in the future; `valid_until` before the quote date; entering a
    quote that has already expired; negative delivery days; blank payment terms; price ≤ 0.
    A quotation that any PO was made from, even a cancelled one, can't be edited or deleted.
    A supplier deactivated after quoting can't be selected.
  - GRNs: received date in the future or before the PO date; a line with 0 received.
  - Invoices: invoice date in the future; total ≤ 0. The duplicate-number check ignores case
    and surrounding spaces.
  - Payments: date in the future or before the invoice date; blank reference number.
  - Masters: GSTIN format and uniqueness; valid unique email; password ≥ 6 characters; an
    ADMIN can't deactivate themselves or change their own role.
  - Money has at most 2 decimals and quantities at most 3. Floats are refused. All problems
    in one request are reported together.
- **Why:** Each blocks data that is clearly wrong or would get stuck. For example, an invoice
  with total 0 could never be paid, so its PO could never close. Stopping these at entry keeps
  them out of the workflow.

### D-49 — The seed is built through the services
- **Source:** Owner (Phase 3 instruction)
- **Decision:** Scenarios call the same service functions the API will call, with the clock
  pinned to each step. Departments, suppliers, items and settings are created by ADMIN through
  `master_service`. Only the 9 demo users are inserted directly, because something has to
  exist before anyone can act. `verify.py` still runs before commit.
- **Why:** The demo data is guaranteed to follow the real rules. For example, the MISMATCH
  reason on SSST/26-27/0923 is produced by the real three-way match.

### D-50 — Expired quotations don't count for rule 6
- **Source:** Owner (Phase 3 review) · 2026-09-24. Replaces the design-pass proposal, which
  counted expired quotes.
- **Decision:** Both checks look only at quotations that have not expired on the day of
  selection. "Fewer than 2 quotations" means fewer than 2 valid ones. "Not the lowest total"
  compares against the lowest valid one. Expired quotations stay in the comparison, flagged
  `is_expired`, with their prices shown. They are never marked lowest (per line or in total)
  and can't be selected (D-14). `verify.py` re-checks each PO against the quotations that
  were valid on the day it was created.
- **Why:** An expired quote is no longer an offer the supplier stands behind. Counting it
  would satisfy "two quotes" with a price nobody can buy at, or force a reason for passing up
  an offer that no longer exists.

### D-51 — Status-dependent refusals are 409; malformed input is 422; a failed match is a result
- **Source:** Design (Phase 3), refines D-27
- **Decision:** Every "not allowed in this status" refusal is a 409 `INVALID_TRANSITION`, even
  when the action doesn't change that status. Examples: a quotation on a non-APPROVED PR, a
  GRN on a SHORT_CLOSED PO, an invoice on an ISSUED PO. Such refusals go through
  `state_machine.require_status`. Invalid input is a 422. A three-way match that fails is not
  an error: the invoice is stored as MISMATCH with one reason per line, in the form
  "Laptop: invoiced 10, accepted 8".
- **Why:** The frontend can treat every 409 as "refresh, the record moved on", and every 422
  as "fix the form". A mismatch has to be recorded, because it is the evidence the control
  exists to capture.

### D-52 — PR edits and deletions are audited and go through the state machine
- **Source:** Design (Phase 3)
- **Decision:** The PR table includes `EDITED` (DRAFT→DRAFT, REJECTED→REJECTED) and `DELETED`
  (DRAFT→gone). Both are checked by the state machine and written to AuditLog like status
  changes. `state_machine.allowed_actions()` exposes what the current status allows, for the UI.
- **Why:** The timeline shows that a rejected PR was changed before resubmission, and a
  deleted draft still leaves a trace.

### D-53 — Line amounts are rounded to the paisa; totals are sums of line amounts
- **Source:** Design (Phase 4; fixes a crash found while building the API)
- **Decision:** `line_amount(qty, price)` = qty × price rounded to 2 places, half up. PR,
  quotation and PO totals, and the invoice-lines sum in the three-way match, are all sums of
  line amounts. Inputs are normalised to column scale (₹600 → 600.00, 50 → 50.000).
- **Why:** Quantities can have 3 decimals (kg), so qty × price can fall below a paisa
  (1.5 × ₹10.01 = ₹15.015). Money columns refuse to round (D-38), so such a PR used to fail
  with a 500. Rounding each line, the way a printed invoice does, keeps every total in the
  system agreeing to the paisa with what a supplier prints.

### D-54 — API conventions
- **Source:** Design (Phase 4)
- **Decision:**
  - Handlers: role check → load the record in the caller's scope (404 if outside it) →
    service → commit → present. No rules in routers.
  - Role check on every endpoint. For GETs the allowed roles come from `access.READ_SCOPES`,
    so the route check and the row scoping can't drift apart.
  - Money and quantities are JSON strings ("73500.00"), so no precision is lost.
  - Lists: `page` / `page_size` (max 100), newest first, `{items, total, page, page_size,
    pages}`. Filters: `status` (repeatable), department, supplier, PO, date range, `q` text.
  - Detail responses carry everything a screen needs. Parts the caller may not read (GRNs for
    FINANCE, invoices for STORE, payments for PURCHASE) come back as `null`, not an error.
    `actions` lists what the caller can do right now; ADMIN always gets `[]`.
  - Action endpoints return the updated detail of the record the screen shows (approve → PR,
    select → the new PO, payment → the invoice, whose `po.status` shows an auto-close).
  - One error body everywhere: `{error, message, details?}`, including unknown routes (404),
    wrong methods (405) and database-constraint conflicts (409 `CONFLICT`).
- **Why:** The frontend can render messages and buttons straight from the API, with no
  permission logic of its own to keep in sync.

### D-55 — Swagger login and test client
- **Source:** Design (Phase 4)
- **Decision:** A hidden `POST /api/auth/token` (OAuth2 password form) lets Swagger's
  Authorize dialog log in with email + demo123. The frontend keeps the JSON `/auth/login`.
  Tests use `httpx2`, which Starlette 1.x's TestClient requires.
- **Why:** The demo can be driven from `/docs` without copying tokens by hand.

### D-56 — Frontend conventions
- **Source:** Design (Phase 5)
- **Decision:**
  - Next.js 14 App Router with client-rendered pages. The JWT is kept in memory and mirrored
    to `sessionStorage`, so each browser tab can be a different demo user and a reload keeps
    you logged in.
  - **Action buttons come only from the API's `actions` list.** The frontend has no
    permission rules of its own. Role is used only to choose sidebar links and the "New
    request" shortcut, and every page is still enforced by the API.
  - Reason fields on quotation selection appear only when the comparison's `selection` hints
    say rule 6 needs them.
  - API error messages are shown verbatim in toasts (bottom-right, so they never cover the
    user switcher).
  - "Switch user" does a full page load to the new user's dashboard. Re-rendering in place
    let the old page refetch as the new user and flash a spurious 403.
  - Money is formatted from the API's decimal strings as text (Indian grouping, ₹6,00,000.00),
    never parsed into floats. Line-total previews in forms are display-only; the server's
    figures replace them on save.
  - System UI font (no web-font download), so a laptop demo works offline.
  - Status colours are by meaning: green done/good, amber waiting, blue in progress, red
    problem, orange exception, grey inert. They are defined once in `lib/status.ts`, and a
    badge always shows its label.
  - Spend-vs-budget chart: one shared ₹ axis, budget as a light track and committed spend as
    the fill, with the reserved red plus an icon and label when over budget. Colours were
    checked with the dataviz palette validator (all checks pass on white).
  - `./dev.sh` in the repo root starts both servers (reusing any already running) and stops
    them on Ctrl-C.
- **Why:** The backend is the only place business rules live (D-26). The frontend's job is to
  show the API's answers clearly to a room watching a laptop.
