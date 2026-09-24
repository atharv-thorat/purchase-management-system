"""Rule 7: the PO copies prices from the selected quotation and never reads them live again."""

from decimal import Decimal

from app.models.enums import POStatus, PRStatus
from app.services import invoice_service, quotation_service
from tests.conftest import DIGITAL, LAPTOP, MOUSE, TECHNO, TWO_LINES

D = Decimal


def test_po_lines_are_a_snapshot_of_the_selected_quotation(w):
    pr = w.approved(lines=TWO_LINES)
    w.quote(pr, TECHNO, {LAPTOP: "990", MOUSE: "95"})
    q = w.quote(pr, DIGITAL, {LAPTOP: "980", MOUSE: "99"})  # 9800 + 1980 = 11780 (lowest)
    po = quotation_service.select_quotation(w.db, w.purchase, pr, q)
    assert po.po_number == "PO-0001"
    assert po.status is POStatus.ISSUED
    assert (po.supplier.name, po.quotation, q.is_selected) == (DIGITAL, q, True)
    assert [(pl.item.name, pl.qty_ordered, pl.unit_price) for pl in po.lines] == \
        [(LAPTOP, D("10"), D("980.00")), (MOUSE, D("20"), D("99.00"))]
    assert po.total == D("11780.00")
    assert [(pl.qty_accepted, pl.qty_invoiced) for pl in po.lines] == [(0, 0), (0, 0)]
    assert pr.status is PRStatus.PO_CREATED
    assert w.audit(po) == [("ISSUED", None, "ISSUED")]
    assert w.audit(pr)[-1] == ("PO_CREATED", "APPROVED", "PO_CREATED")


def test_changing_the_quotation_afterwards_does_not_touch_the_po(w):
    po = w.po(prices={LAPTOP: "900"})
    po.quotation.lines[0].unit_price = D("1200")  # simulate a later change at the source
    w.db.flush()
    assert po.lines[0].unit_price == D("900.00")
    w.receive(po)
    inv = w.invoice(po, lines={LAPTOP: ("10", "900")})
    assert inv.status == "MATCHED"  # matched against the snapshot, not the quotation


def test_invoice_at_the_quotations_new_price_mismatches(w):
    po = w.po(prices={LAPTOP: "900"})
    po.quotation.lines[0].unit_price = D("1200")
    w.receive(po)
    inv = w.invoice(po, lines={LAPTOP: ("10", "1200")})
    assert inv.status == "MISMATCH"
    assert invoice_service.three_way_match(inv)[0].endswith("does not match PO price ₹900.00")
