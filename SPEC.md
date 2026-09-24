# Purchase Management System — Specification

> Revision 2 (2026-09-24): open questions from the design pass resolved. Each change is
> logged with its reason in [DECISIONS.md](DECISIONS.md) (D-numbers referenced below).

## Business problem
Departments in a company need to buy goods (laptops, raw material, stationery). Uncontrolled
buying causes overspending, duplicate orders, fake invoices, and paying for goods never received.
This system controls the full procure-to-pay (P2P) cycle:

Purchase Request → Approval → Supplier Quotations → Comparison & Selection → Purchase Order
→ Goods Receipt (GRN) → Supplier Invoice → Three-Way Match → Payment → PO Closure

This is a WORKFLOW application, not a CRUD app. Every entity has a status, and status changes
happen only through defined actions with business-rule validation.

## Tech stack
- Backend: Python, FastAPI, SQLAlchemy 2.x, Pydantic v2, SQLite (file-based, zero setup), pytest
- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS
- Auth: simple JWT login with seeded demo users; role-based access on every endpoint
- Must run locally with one command each for backend and frontend (for a live laptop demo)

## Roles (segregation of duties)
- REQUESTER — raises purchase requests for their department
- DEPT_HEAD — approves/rejects PRs of their own department only; may also raise PRs, which
  escalate straight to FINANCE (D-01)
- FINANCE — second-level approval for high-value PRs, and sole approver of PRs raised by a
  DEPT_HEAD
- PURCHASE — records supplier quotations, compares, selects, creates POs, cancels and
  short-closes POs
- STORE — records goods receipts
- ACCOUNTS — records supplier invoices, runs three-way match, rematches/rejects mismatched
  invoices, records payments
- ADMIN — manages departments, users, suppliers, items, settings. Read-only access to all
  transactional data; takes NO transactional actions (D-09)

Rules:
- Nobody can approve their own request.
- Each user has exactly one role (D-22).
- Only REQUESTER and DEPT_HEAD users raise PRs; other roles have no department (D-19).

Read visibility (D-08):
- REQUESTER — own PRs, plus the POs, GRNs and invoices (incl. payment status) linked to them
- DEPT_HEAD — the same, for every PR in their department
- FINANCE — all PRs, POs, invoices, payments
- PURCHASE — PRs from APPROVED onwards, quotations, POs, GRNs, invoices
- STORE — POs, GRNs
- ACCOUNTS — POs, GRNs, invoices, payments
- ADMIN — everything, read-only

## Entities
- Department: name, monthly_budget
- User: name, email, password_hash, role, department_id (nullable), is_active (D-23)
- Supplier: name, contact_person, email, phone, gstin, is_active
- Item: name, unit (pcs/kg/box), category
- Setting: key/value (e.g. FINANCE_APPROVAL_THRESHOLD = 50000)
- PurchaseRequest: pr_number (PR-0001), requester, department, justification, required_by,
  status, estimated_total, rejection_reason, final_approved_at, timestamps
- PRLine: pr, item, quantity, estimated_unit_price
- Quotation: pr, supplier, quote_date, valid_until, delivery_days, payment_terms, total
  (computed), is_selected
- QuotationLine: quotation, pr_line, unit_price
- PurchaseOrder: po_number (PO-0001), pr, quotation, supplier, status, total,
  selection_reason, single_quote_justification, cancel_reason, short_close_reason,
  created_by, timestamps
- POLine: po, item, qty_ordered, unit_price (SNAPSHOT copied from quotation — never read live),
  qty_accepted (cumulative), qty_invoiced (cumulative, MATCHED invoices only)
- GoodsReceipt: grn_number (GRN-0001), po, received_by, received_date, remarks
- GRNLine: grn, po_line, qty_received, qty_accepted, qty_rejected, rejection_reason
- Invoice: supplier_invoice_number, po, supplier, invoice_date, total, status, mismatch_details,
  rejection_reason, created_by
- InvoiceLine: invoice, po_line, qty, unit_price
- Payment: invoice, amount, mode (NEFT/CHEQUE/UPI), reference_no, paid_on, recorded_by
- ApprovalLog: pr, level (DEPT_HEAD/FINANCE), approver, action (APPROVED/REJECTED), comment,
  over_budget, at
- AuditLog: entity_type, entity_id, action, from_status, to_status, user, at, details

## Status machines
- PR:
  - DRAFT → PENDING_DEPT_HEAD (requester is REQUESTER) or → PENDING_FINANCE (requester is
    DEPT_HEAD, regardless of amount — D-01)
  - PENDING_DEPT_HEAD → PENDING_FINANCE if above threshold, else → APPROVED
  - PENDING_FINANCE → APPROVED
  - APPROVED → PO_CREATED; PO_CREATED → APPROVED when its PO is cancelled (D-06)
  - any pending state → REJECTED; REJECTED → (edit & resubmit) → same entry state as submit
    (the full approval chain restarts — D-02)
  - DRAFT can be deleted; there is no CANCELLED state for PRs (D-13)
- PO: ISSUED → PARTIALLY_RECEIVED → FULLY_RECEIVED → CLOSED; ISSUED → CANCELLED;
  PARTIALLY_RECEIVED → SHORT_CLOSED → CLOSED (D-07)
- Invoice: PENDING_MATCH → MATCHED or MISMATCH; MATCHED → PARTIALLY_PAID → PAID
  (or MATCHED → PAID directly); MISMATCH → (rematch) → PENDING_MATCH; MISMATCH → REJECTED
  (D-03)
Invalid transitions must be rejected by the backend with a clear error message.

## Business rules
1. Approval routing: PR raised by a REQUESTER with estimated_total ≤
   FINANCE_APPROVAL_THRESHOLD → DEPT_HEAD only. Above threshold → DEPT_HEAD then FINANCE.
   The threshold is read when the DEPT_HEAD approves (D-12). PR raised by a DEPT_HEAD →
   FINANCE only, regardless of amount (D-01). Threshold is configurable in Settings.
2. DEPT_HEAD can only act on PRs from their own department. Nobody can approve their own PR.
3. Rejection requires a comment. Requester can edit a REJECTED PR and resubmit; the approval
   chain restarts from the beginning (D-02).
4. Budget check: if department's approved total this month + this PR's estimated_total >
   monthly_budget, show a visible "Over budget" warning to approvers (approval still allowed,
   but logged in ApprovalLog.over_budget). "Approved total this month" (D-05) =
   sum over the department's PRs in status APPROVED or PO_CREATED whose final approval date
   falls in the current calendar month, valued at the non-cancelled PO total if a PO exists,
   else the PR estimated_total. The PR being approved is excluded from the sum.
5. Quotations can only be added to APPROVED PRs. Each quotation must price every PR line.
   Quantities always equal the PR quantities; quotation total is computed (D-15). At most one
   quotation per supplier per PR (D-16). Supplier must be active.
6. Selecting a quotation: if fewer than 2 quotations exist, single_quote_justification is
   required. If the selected quotation is not the lowest total, selection_reason is required.
   An expired quotation (valid_until < today) cannot be selected (D-14).
7. Creating a PO copies prices from the selected quotation into POLines. PR → PO_CREATED.
   Selection and PO creation are one atomic action.
8. PO can be CANCELLED (reason required) only if no GRN exists against it, even one with
   everything rejected (D-17). Cancelling returns the PR to APPROVED and clears the quotation
   selection so a new PO can be created. One-PR-one-PO applies to non-cancelled POs only (D-06).
9. GRN: for each line, qty_accepted + qty_rejected = qty_received; cumulative qty_accepted
   cannot exceed qty_ordered. PO status auto-updates from accepted quantities (D-18):
   nothing accepted → stays ISSUED; some accepted → PARTIALLY_RECEIVED; all accepted →
   FULLY_RECEIVED. GRNs allowed only on ISSUED / PARTIALLY_RECEIVED POs.
10. Three-way match (core rule) on invoice entry, per line:
    - invoice unit_price must equal PO line unit_price exactly (to the paisa — D-21)
    - (already invoiced qty + this invoice qty) must be ≤ qty_accepted from GRNs, where
      "already invoiced" counts MATCHED invoices only (D-04)
    - invoice total must equal Σ(qty × unit_price) of its lines (D-20)
    If all checks pass → MATCHED. Otherwise → MISMATCH, with a human-readable list of every
    failing line and reason stored in mismatch_details (e.g. "Laptop: invoiced 10, accepted 8").
    Invoices can be entered only against PARTIALLY_RECEIVED, FULLY_RECEIVED or SHORT_CLOSED
    POs (D-25).
10a. MISMATCH invoices (D-03): ACCOUNTS can
    - **rematch** — re-run the three-way match against current GRN/invoice data (e.g. after a
      late GRN); invoice lines are not edited; or
    - **reject** (reason required) → REJECTED, a terminal state. The supplier then issues a
      corrected invoice, which is entered fresh.
11. Duplicate supplier_invoice_number for the same supplier is blocked, excluding REJECTED
    invoices (D-03).
12. Payments allowed only on MATCHED / PARTIALLY_PAID invoices. Partial payments allowed.
    Total paid cannot exceed invoice total. Invoice → PAID when fully paid.
13. Short-close (D-07): PURCHASE can short-close a PARTIALLY_RECEIVED PO with a mandatory
    reason → SHORT_CLOSED. No further GRNs are allowed; invoicing and payment of accepted
    quantities continue.
14. PO auto-CLOSES (from FULLY_RECEIVED or SHORT_CLOSED) when every line's qty_invoiced =
    qty_accepted and every non-REJECTED invoice on the PO is PAID. Checked after every
    payment, invoice rejection and short-close.
15. Every status change writes an AuditLog entry.

## Assumptions (state these in the README)
- Single company, multiple departments, single currency (INR)
- Prices are GST-inclusive
- One PR → one active PO (PR splitting across suppliers is a future enhancement)
- Payments are recorded, not processed through a real gateway
- Quotations are entered by the purchase officer (no supplier portal)
- Suppliers are created by ADMIN only (D-10)
- "Month" means calendar month in server local time (IST)

## Frontend pages
- Login page with one-click demo-user buttons for each role (for fast live demo)
- Role-based sidebar showing only what that role can do
- Dashboard: pending approvals, open POs by status, invoices with MISMATCH, pending payments,
  spend by department this month vs budget, recent activity (from AuditLog)
- PR: list, create (multi-line items), detail with approval timeline, approve/reject
- Quotations: add per PR, side-by-side comparison table highlighting lowest price per line
  and lowest total, select-and-create-PO action
- PO: list, detail showing ordered / accepted / invoiced quantities per line and linked
  GRNs, invoices, payments; cancel and short-close actions (PURCHASE)
- GRN: record receipt against a PO (pre-filled with pending quantities)
- Invoice: enter against a PO, shows match result clearly (green MATCHED / red MISMATCH
  with reasons); rematch and reject actions on MISMATCH
- Payments: record against invoice, shows balance due
- Masters (ADMIN): departments, users, suppliers, items, settings
- Every detail page shows a status badge and a status timeline
- ADMIN sees all transactional pages read-only (no action buttons)

## Seed data
- Departments: IT (budget 10,00,000), Operations (5,00,000), HR (2,00,000)
- Demo users (password: demo123) — 9 in total (D-24): REQUESTER and DEPT_HEAD in both IT and
  Operations, plus one each of FINANCE, PURCHASE, STORE, ACCOUNTS, ADMIN. HR has no users.
- 5 suppliers, 12 items
- Sample records in varied states: one PR pending approval, one approved PR with 3 quotes,
  one PO partially received, one invoice in MISMATCH, one fully closed PO

## Quality requirements
- Business rules live in a service layer (not in route handlers), each rule unit-tested
- pytest tests covering: approval routing (incl. DEPT_HEAD escalation to FINANCE),
  self-approval block, partial GRN, three-way match pass and fail, invoice rematch and
  reject, duplicate invoice (incl. REJECTED exclusion), overpayment block, PO cancel
  returning PR to APPROVED, short-close, PO auto-close, budget warning
- README with setup steps, assumptions, process flow, and demo script
- Maintain DECISIONS.md: log each significant design decision and why
