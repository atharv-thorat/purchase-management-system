"""Mutation check: prove the tests would notice if a business rule were broken.

Each mutant below disables one rule in the service layer. For each, the source is patched,
the test suite runs, and the file is restored (always — even on Ctrl-C). A mutant that
"survives" (tests still pass) means that rule is not really tested.

    cd backend && .venv/bin/python tools/mutation_check.py
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# (rule, file, original code, broken code)
MUTANTS = [
    ("Nobody approves their own PR (rule 2)", "app/services/pr_service.py",
     'if actor.id == pr.requester_id:\n        raise Forbidden(f"You cannot', 'if False:\n        raise Forbidden(f"You cannot'),
    ("Dept-head PRs go straight to FINANCE (D-01)", "app/services/pr_service.py",
     "target = PRStatus.PENDING_FINANCE if actor.role is Role.DEPT_HEAD else PRStatus.PENDING_DEPT_HEAD",
     "target = PRStatus.PENDING_DEPT_HEAD"),
    ("Above threshold needs FINANCE (rule 1)", "app/services/pr_service.py",
     "pr.estimated_total > finance_threshold(db)", "pr.estimated_total > finance_threshold(db) * 1000"),
    ("Budget month = current calendar month (D-05)", "app/services/pr_service.py",
     "PurchaseRequest.final_approved_at >= clock.month_start(),", ""),
    ("Expired quotes don't count for rule 6 (D-50)", "app/services/quotation_service.py",
     "valid = valid_quotations(pr)", "valid = list(pr.quotations)"),
    ("Any GRN blocks PO cancel (D-17)", "app/services/po_service.py",
     "if po.goods_receipts:", "if any(pl.qty_accepted for pl in po.lines):"),
    ("Cumulative accepted ≤ ordered (rule 9)", "app/services/grn_service.py",
     "if pl.qty_accepted + accepted > pl.qty_ordered:", "if False:"),
    ("Price must match the PO exactly (D-21)", "app/services/invoice_service.py",
     "if il.unit_price != pl.unit_price:", "if abs(il.unit_price - pl.unit_price) > 1:"),
    ("Only MATCHED invoices count as invoiced (D-04)", "app/services/invoice_service.py",
     '        invoice.mismatch_details = "\\n".join(failures)\n',
     '        invoice.mismatch_details = "\\n".join(failures)\n        for il in invoice.lines:\n'
     '            il.po_line.qty_invoiced += min(il.qty, il.po_line.qty_accepted - il.po_line.qty_invoiced)\n'),
    ("REJECTED invoices free their number (rule 11)", "app/services/invoice_service.py",
     "Invoice.status != InvoiceStatus.REJECTED,", ""),
    ("No overpayment (rule 12)", "app/services/payment_service.py",
     "if amount > balance:", "if amount > balance + 1000000:"),
    ("Open MISMATCH blocks PO auto-close (D-34)", "app/services/po_service.py",
     "live = [inv for inv in po.invoices if inv.status is not InvoiceStatus.REJECTED]",
     "live = [inv for inv in po.invoices if inv.status not in (InvoiceStatus.REJECTED, InvoiceStatus.MISMATCH)]"),
    ("Every status change is audited (rule 15)", "app/services/state_machine.py",
     "    record_status_change(\n        db,\n        entity_type=entity_type,\n        entity_id=entity.id,\n        action=action,\n        from_status=from_status,",
     "    if False: record_status_change(\n        db,\n        entity_type=entity_type,\n        entity_id=entity.id,\n        action=action,\n        from_status=from_status,"),
]


def run_tests() -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "-o", "addopts="],
        cwd=BACKEND, capture_output=True, text=True,
    )
    failed = next((ln.split(" ", 1)[1] for ln in result.stdout.splitlines() if ln.startswith(("FAILED ", "ERROR "))), "")
    return result.returncode != 0, failed


def main() -> int:
    survivors = 0
    for rule, rel_path, original, broken in MUTANTS:
        path = BACKEND / rel_path
        source = path.read_text()
        if original not in source:
            print(f"  SKIPPED   {rule}: pattern not found in {rel_path} (update this mutant)")
            survivors += 1
            continue
        path.write_text(source.replace(original, broken, 1))
        try:
            caught, first_failure = run_tests()
        finally:
            path.write_text(source)
        survivors += not caught
        verdict = "caught  " if caught else "SURVIVED"
        print(f"  {verdict}  {rule:<48} {first_failure.split(' - ')[0][:70]}")
    print(f"\n{len(MUTANTS) - survivors}/{len(MUTANTS)} broken rules caught by the tests.")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
