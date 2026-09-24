# Demo cheat sheet

**Before:** `./dev.sh --reset` → open http://localhost:3000 (password `demo123` for everyone; works
offline). **If anything goes wrong mid-demo:** run `./dev.sh --reset` in a second terminal (2 s),
then switch user once to reload.
Switch users from the name menu at the top right.

## Steps

| # | Log in as | Do | Say |
|---|---|---|---|
| 1 | **Karan** · Requester, Ops | New request: 50 **Safety Helmet** @600 + 30 **Packaging Tape** @1450 → Save draft → Submit | ₹73,500 → goes to his dept head |
| 2 | **Neha** · Dept head, Ops | Approvals → **PR-0007** | Over-budget warning; approval still allowed, warning logged |
| 3 | Neha | **PR-0009** → Approve | > ₹50,000 → Pending finance |
| 4 | **Arjun** · Dept head, IT | **PR-0006** (his own) | No approve button: own PRs go to Finance |
| 5 | **Priya** · Finance | Dashboard → approve PR-0009 | Spend vs budget chart |
| 6 | **Vikram** · Purchase | PR-0009 → Quotations & PO → add Shree 560/1500 (3 d), Bharat 590/1380 (5 d), Techno 640/1400 (10 d) | Lowest per line + lowest valid total |
| 7 | Vikram | Select **Shree** → Create (fails) → give a reason → Create | Rule 6 message comes from the API; PO-0004 issued, prices frozen |
| 8 | **Suresh** · Store | PO-0004 → Record receipt: received 45, rejected 5 "Cracked" | Pre-filled; Partially received |
| 9 | **Anita** · Accounts | PO-0004 → Enter invoice SSST/26-27/1102, helmets qty **50** | **MISMATCH**: invoiced 50, accepted 40 |
| 10 | Suresh | PO-0004 → Record receipt (remaining 10) | Fully received |
| 11 | Anita | Invoice → Rematch → pay 50,000 → try 99,999 → pay 23,000 | MATCHED; overpay refused; **PO auto-closes** |
| 12 | Anita | PO-0004 | Progress bars, GRNs, invoice, payments, full timeline |
| 13 | **Meera** · Admin | Any PR/PO, Masters | Reads everything, no buttons |

Extras if there's time: **PO-0002** (short-closed; pay ₹38,000 → closes) · **SSST/26-27/0923** (seeded
mismatch → Reject) · **PR-0004** (rejected; Karan edits + resubmits → chain restarts) ·
http://localhost:8000/docs (Authorize: `finance@example.com` / `demo123`).

## Likely questions

**1. Where do the business rules live, and how do you stop them leaking into the UI?**
Only in the service layer; routers check the role, load the record in scope, call one service, commit.
Every detail response carries `actions` for the current user, and the UI renders exactly those buttons.
→ `backend/app/services/pr_service.py` (`approve_pr`), `backend/app/services/actions.py`,
`frontend/src/app/(app)/prs/[id]/page.tsx` (`has("approve")`).

**2. How does the three-way match work, and what happens when it fails?**
Per line: price = PO price to the paisa; already-invoiced + this ≤ accepted; printed total = sum of
lines. A failure isn't an error — the invoice is saved as MISMATCH with every reason; only matched
invoices count as invoiced, so a correct invoice can still match later. Rematch or reject.
→ `backend/app/services/invoice_service.py` (`three_way_match`), `tests/test_three_way_match.py`.

**3. How do you enforce segregation of duties and "need to know"?**
Three layers: role gate on every endpoint (403), row-level read scopes per role (out-of-scope = 404, so
existence isn't leaked), and rule checks in services (self-approval, department, level). Admin never
appears in any transactional role list.
→ `backend/app/services/access.py` (`READ_SCOPES`), `tests/test_service_rbac.py`, `tests/test_access_scoping.py`.

**4. How do you know a status can't be changed illegally, or without a trace?**
One state machine with explicit `(status, action) → allowed targets` tables; `transition()` checks the
table and writes the audit row. Each action runs in a savepoint, so a failure rolls back status, audit
and document number together. Every status × action pair is tested (342 cases); a mutation check breaks
13 rules and the tests catch all of them.
→ `backend/app/services/state_machine.py`, `backend/app/core/db.py` (`atomic`), `backend/tools/mutation_check.py`.

**5. How is money kept exact?**
Stored as integer paise, handled as `Decimal`, floats refused; each line amount rounds half-up to the
paisa and totals are sums of lines — the same rule the frontend uses for previews, without floats, so a
pre-filled invoice total never causes a false mismatch.
→ `backend/app/models/types.py` (`Money`), `backend/app/services/_common.py` (`line_amount`),
`frontend/src/lib/decimal.ts`; DECISIONS D-38, D-53, D-57.

*Also ready:* why SQLite? (zero setup; writes serialised with `BEGIN IMMEDIATE`, Postgres for
production — D-47) · why 404 not 403? (D-37) · why expired quotes don't count? (D-50).
