"""The full procure-to-pay demo over HTTP, each step by the role that owns it:
PR → dept head → finance → quotations → select → GRN → invoice (MISMATCH) → late GRN → rematch
→ payments → PO auto-closes. Plus the seeded demo scenarios."""

from app.models import Invoice, PurchaseOrder, PurchaseRequest

TODAY = "2026-09-15"  # tests.conftest.NOW


def _ids(api):
    purchase = api.as_("purchase")
    items = {i["name"]: i["id"] for i in api.as_("requester.ops").get("/api/items").json()}
    suppliers = {s["name"]: s["id"] for s in purchase.get("/api/suppliers", params={"active": True}).json()}
    return items, suppliers


def test_full_procure_to_pay_flow(api):
    items, suppliers = _ids(api)
    karan, neha, priya = api.as_("requester.ops"), api.as_("head.ops"), api.as_("finance")
    vikram, suresh, anita = api.as_("purchase"), api.as_("store"), api.as_("accounts")

    # 1. Requester raises and submits a ₹73,500 PR (above the ₹50,000 finance threshold)
    r = karan.post("/api/prs", json={
        "justification": "Safety kit and packing material for the Bay 3 crew",
        "required_by": "2026-10-15",
        "lines": [{"item_id": items["Safety Helmet"], "quantity": "50", "estimated_unit_price": "600"},
                  {"item_id": items["Packaging Tape (box of 36)"], "quantity": "30", "estimated_unit_price": "1450"}],
    })
    assert r.status_code == 201, r.text
    pr = r.json()
    assert (pr["pr_number"], pr["status"], pr["estimated_total"]) == ("PR-0009", "DRAFT", "73500.00")
    assert pr["actions"] == ["edit", "delete", "submit"]
    pr_id = pr["id"]
    pr = karan.post(f"/api/prs/{pr_id}/submit").json()
    assert pr["status"] == "PENDING_DEPT_HEAD" and pr["actions"] == []

    # 2. Dept head sees it in the inbox with the budget check, and approves → FINANCE
    inbox = neha.get("/api/approvals/pending").json()
    mine = next(p for p in inbox if p["id"] == pr_id)
    assert mine["level"] == "DEPT_HEAD"
    assert (mine["budget"]["approved_this_month"], mine["budget"]["over_budget"]) == ("55000.00", False)
    assert neha.get(f"/api/prs/{pr_id}").json()["actions"] == ["approve", "reject"]
    pr = neha.post(f"/api/prs/{pr_id}/approve", json={"comment": "Needed before go-live"}).json()
    assert pr["status"] == "PENDING_FINANCE"

    # 3. Finance approves → APPROVED
    pr = priya.post(f"/api/prs/{pr_id}/approve").json()
    assert pr["status"] == "APPROVED"
    assert [a["level"] for a in pr["approvals"]] == ["DEPT_HEAD", "FINANCE"]
    assert [t["action"] for t in pr["timeline"]] == ["CREATED", "SUBMITTED", "APPROVED", "APPROVED"]

    # 4. Purchase records three quotations
    helmet_line, tape_line = (ln["id"] for ln in pr["lines"])

    def quote(supplier, helmet, tape, days):
        r = vikram.post(f"/api/prs/{pr_id}/quotations", json={
            "supplier_id": suppliers[supplier], "quote_date": TODAY, "valid_until": "2026-10-15",
            "delivery_days": days, "payment_terms": "30 days",
            "lines": [{"pr_line_id": helmet_line, "unit_price": helmet}, {"pr_line_id": tape_line, "unit_price": tape}]})
        assert r.status_code == 201, r.text
        return r.json()

    shree = quote("Shree Steel & Safety Traders", "560", "1500", 3)  # 28000 + 45000 = 73000
    bharat = quote("Bharat Office Supplies", "590", "1380", 5)  # 29500 + 41400 = 70900 (lowest)
    quote("Techno Solutions Pvt Ltd", "640", "1400", 10)  # 32000 + 42000 = 74000
    cmp = vikram.get(f"/api/prs/{pr_id}/quotations/comparison").json()
    assert cmp["selection"] == {"valid_quotations": 3, "single_quote_justification_required": False,
                                "lowest_valid_total": "70900.00", "lowest_valid_quotation_ids": [bharat["id"]]}
    helmet_row = cmp["lines"][0]
    assert [c["quotation_id"] for c in helmet_row["cells"] if c["is_lowest"]] == [shree["id"]]

    # 5. Selecting the faster, dearer supplier needs a reason
    r = vikram.post(f"/api/prs/{pr_id}/quotations/{shree['id']}/select", json={})
    assert r.status_code == 422
    assert r.json()["message"].startswith("The quotation from Shree Steel & Safety Traders (₹73,000.00) is not the "
                                          "lowest valid one (₹70,900.00 from Bharat Office Supplies)")
    r = vikram.post(f"/api/prs/{pr_id}/quotations/{shree['id']}/select",
                    json={"selection_reason": "3-day delivery; Bharat needs 5 and go-live is Monday"})
    assert r.status_code == 201, r.text
    po = r.json()
    po_id = po["id"]
    assert (po["po_number"], po["status"], po["total"]) == ("PO-0004", "ISSUED", "73000.00")
    assert [(ln["unit_price"], ln["qty_ordered"]) for ln in po["lines"]] == [("560.00", "50.000"),
                                                                             ("1500.00", "30.000")]
    assert karan.get(f"/api/prs/{pr_id}").json()["status"] == "PO_CREATED"

    # 6. Store receives part of it (5 helmets cracked)
    receivable = suresh.get(f"/api/pos/{po_id}/receivable").json()
    lines = {ln["item"]["name"]: ln for ln in receivable["lines"]}
    r = suresh.post(f"/api/pos/{po_id}/grns", json={"received_date": TODAY, "lines": [
        {"po_line_id": lines["Safety Helmet"]["po_line_id"], "qty_received": "45", "qty_accepted": "40",
         "qty_rejected": "5", "rejection_reason": "Cracked shells"},
        {"po_line_id": lines["Packaging Tape (box of 36)"]["po_line_id"], "qty_received": "30", "qty_accepted": "30"}]})
    assert r.status_code == 201, r.text
    assert (r.json()["grn_number"], r.json()["po"]["status"]) == ("GRN-0004", "PARTIALLY_RECEIVED")

    # 7. Accounts enters the supplier's invoice for all 50 helmets → MISMATCH
    inv_body = {"supplier_invoice_number": "SSST/26-27/1102", "invoice_date": TODAY, "total": "73000",
                "lines": [{"po_line_id": lines["Safety Helmet"]["po_line_id"], "qty": "50", "unit_price": "560"},
                          {"po_line_id": lines["Packaging Tape (box of 36)"]["po_line_id"], "qty": "30",
                           "unit_price": "1500"}]}
    r = anita.post(f"/api/pos/{po_id}/invoices", json=inv_body)
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["status"] == "MISMATCH"
    assert inv["mismatch_reasons"] == ["Safety Helmet: invoiced 50, accepted 40"]
    assert inv["actions"] == ["rematch", "reject"]
    inv_id = inv["id"]
    assert anita.post(f"/api/invoices/{inv_id}/payments", json={
        "amount": "1", "mode": "NEFT", "reference_no": "X", "paid_on": TODAY}).status_code == 409

    # 8. Replacement helmets arrive; 9. rematch → MATCHED
    r = suresh.post(f"/api/pos/{po_id}/grns", json={"received_date": TODAY, "lines": [
        {"po_line_id": lines["Safety Helmet"]["po_line_id"], "qty_received": "10", "qty_accepted": "10"}]})
    assert r.json()["po"]["status"] == "FULLY_RECEIVED"
    inv = anita.post(f"/api/invoices/{inv_id}/rematch").json()
    assert (inv["status"], inv["mismatch_reasons"], inv["balance_due"]) == ("MATCHED", [], "73000.00")

    # 10. Payments: part, an attempted overpayment, then the balance → PO closes itself
    inv = anita.post(f"/api/invoices/{inv_id}/payments", json={
        "amount": "50000", "mode": "NEFT", "reference_no": "UTR-1", "paid_on": TODAY}).json()
    assert (inv["status"], inv["balance_due"], inv["po"]["status"]) == ("PARTIALLY_PAID", "23000.00", "FULLY_RECEIVED")
    r = anita.post(f"/api/invoices/{inv_id}/payments", json={
        "amount": "23000.01", "mode": "UPI", "reference_no": "UTR-2", "paid_on": TODAY})
    assert r.status_code == 422
    assert r.json() == {"error": "BUSINESS_RULE_VIOLATION", "message": "Payment of ₹23,000.01 exceeds the balance "
                        "due of ₹23,000.00 on invoice SSST/26-27/1102"}
    inv = anita.post(f"/api/invoices/{inv_id}/payments", json={
        "amount": "23000", "mode": "UPI", "reference_no": "UTR-2", "paid_on": TODAY}).json()
    assert (inv["status"], inv["po"]["status"], inv["actions"]) == ("PAID", "CLOSED", [])

    # The PO detail has the whole story in one call
    po = vikram.get(f"/api/pos/{po_id}").json()
    assert [(ln["qty_ordered"], ln["qty_accepted"], ln["qty_invoiced"], ln["qty_pending_receipt"])
            for ln in po["lines"]] == [("50.000", "50.000", "50.000", "0.000"), ("30.000", "30.000", "30.000", "0.000")]
    assert [g["grn_number"] for g in po["goods_receipts"]] == ["GRN-0004", "GRN-0005"]
    assert [i["status"] for i in po["invoices"]] == ["PAID"]
    assert po["payments"] is None  # PURCHASE doesn't see payments
    assert [t["action"] for t in po["timeline"]] == [
        "ISSUED", "GRN_RECORDED", "ENTERED", "MISMATCHED", "GRN_RECORDED", "REMATCH_REQUESTED", "MATCHED",
        "PAYMENT_RECORDED", "PAYMENT_RECORDED", "CLOSED"]
    requester_view = karan.get(f"/api/pos/{po_id}").json()
    assert (len(requester_view["payments"]), requester_view["actions"]) == (2, [])


def test_seeded_scenarios_finish_through_the_api(api):
    arjun, priya, vikram, anita = (api.as_(k) for k in ("head.it", "finance", "purchase", "accounts"))

    # PR-0006: the IT head's own PR waits on Finance; he cannot approve it himself
    pr6 = api.id(PurchaseRequest, "PR-0006")
    r = arjun.post(f"/api/prs/{pr6}/approve")
    assert (r.status_code, r.json()["message"]) == (403, "You cannot approve your own purchase request")
    assert priya.post(f"/api/prs/{pr6}/approve").json()["status"] == "APPROVED"

    # PO-0002 (SHORT_CLOSED): paying the ₹38,000 balance closes it
    inv = anita.get("/api/invoices", params={"po_id": api.id(PurchaseOrder, "PO-0002"),
                                              "status": "PARTIALLY_PAID"}).json()["items"][0]
    paid = anita.post(f"/api/invoices/{inv['id']}/payments", json={
        "amount": inv["balance_due"], "mode": "NEFT", "reference_no": "UTR-9", "paid_on": TODAY}).json()
    assert (paid["status"], paid["po"]["status"]) == ("PAID", "CLOSED")

    # SSST/26-27/0923 (MISMATCH): reject it, then the corrected invoice under the same number matches
    bad = api.id(Invoice, "SSST/26-27/0923")
    rejected = anita.post(f"/api/invoices/{bad}/reject", json={"reason": "Billed for 20 kg that we rejected"}).json()
    assert rejected["status"] == "REJECTED"
    po3 = vikram.get(f"/api/pos/{api.id(PurchaseOrder, 'PO-0003')}").json()
    steel, helmet = po3["lines"]
    corrected = anita.post(f"/api/pos/{po3['id']}/invoices", json={
        "supplier_invoice_number": "SSST/26-27/0923", "invoice_date": TODAY, "total": "35640",
        "lines": [{"po_line_id": steel["id"], "qty": "280", "unit_price": "88"},
                  {"po_line_id": helmet["id"], "qty": "20", "unit_price": "550"}]}).json()
    assert corrected["status"] == "MATCHED"

    # PR-0005: three quotes; Infoline is the lowest valid total
    pr5 = api.id(PurchaseRequest, "PR-0005")
    cmp = vikram.get(f"/api/prs/{pr5}/quotations/comparison").json()
    by_supplier = {q["supplier"]["name"]: q for q in cmp["quotations"]}
    assert by_supplier["Infoline Computers"]["is_lowest_valid_total"]
    techno = by_supplier["Techno Solutions Pvt Ltd"]["quotation_id"]
    po = vikram.post(f"/api/prs/{pr5}/quotations/{techno}/select",
                     json={"selection_reason": "7-day delivery vs 21; hires start next month"}).json()
    # ... then cancel that PO: the PR returns to APPROVED and can be re-sourced
    cancelled = vikram.post(f"/api/pos/{po['id']}/cancel", json={"reason": "Techno withdrew the offer"}).json()
    assert cancelled["status"] == "CANCELLED"
    pr = vikram.get(f"/api/prs/{pr5}").json()
    assert (pr["status"], pr["actions"]) == ("APPROVED", ["add_quotation", "select_quotation"])
    assert [p["status"] for p in pr["purchase_orders"]] == ["CANCELLED"]


def test_short_close_via_api(api):
    vikram = api.as_("purchase")
    po3 = api.id(PurchaseOrder, "PO-0003")
    assert vikram.get(f"/api/pos/{po3}").json()["actions"] == ["short_close"]
    po = vikram.post(f"/api/pos/{po3}/short-close", json={"reason": "Balance steel no longer needed"}).json()
    assert po["status"] == "SHORT_CLOSED"  # the open MISMATCH invoice keeps it from closing
    assert api.as_("store").post(f"/api/pos/{po3}/grns", json={"received_date": TODAY, "lines": [
        {"po_line_id": po["lines"][0]["id"], "qty_received": "1", "qty_accepted": "1"}]}).status_code == 409
