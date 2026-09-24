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
  laptop's timezone. Tests can pin the clock by patching one function.

### D-41 — Seed writes history directly and must pass an invariant check
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
