"""Rule 11: duplicate supplier invoice numbers are blocked, except against REJECTED ones (D-03)."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core import clock
from app.core.errors import BusinessRuleViolation
from app.models import Invoice
from app.services import invoice_service
from tests.conftest import DIGITAL, LAPTOP


def _received(w, supplier=None):
    po = w.po(supplier=supplier) if supplier else w.po()
    w.receive(po, accept={LAPTOP: "4"})
    return po


def test_same_supplier_same_number_is_blocked(w):
    po = _received(w)
    w.invoice(po, "INF/0412", lines={LAPTOP: ("2", "1000")})
    with pytest.raises(BusinessRuleViolation) as exc:
        w.invoice(po, "INF/0412", lines={LAPTOP: ("2", "1000")})
    assert exc.value.message == (f"Invoice INF/0412 from {po.supplier.name} is already recorded against "
                                 f"{po.po_number} (MATCHED)")


def test_duplicate_check_spans_pos_of_the_same_supplier(w):
    po1, po2 = _received(w), _received(w)
    w.invoice(po1, "INF/0412", lines={LAPTOP: ("2", "1000")})
    with pytest.raises(BusinessRuleViolation, match=f"already recorded against {po1.po_number}"):
        w.invoice(po2, "INF/0412", lines={LAPTOP: ("2", "1000")})


def test_case_and_surrounding_spaces_do_not_make_a_new_number(w):
    po = _received(w)
    w.invoice(po, "inf/0412", lines={LAPTOP: ("2", "1000")})
    with pytest.raises(BusinessRuleViolation, match="already recorded"):
        w.invoice(po, "  INF/0412 ", lines={LAPTOP: ("2", "1000")})


def test_mismatched_invoice_still_blocks_its_number(w):
    po = _received(w)
    w.invoice(po, "INF/0412", lines={LAPTOP: ("9", "1000")})  # MISMATCH
    with pytest.raises(BusinessRuleViolation, match=r"\(MISMATCH\)"):
        w.invoice(po, "INF/0412", lines={LAPTOP: ("4", "1000")})


def test_rejected_invoice_frees_its_number(w):
    po = _received(w)
    bad = w.invoice(po, "INF/0412", lines={LAPTOP: ("9", "1000")})
    invoice_service.reject_invoice(w.db, w.accounts, bad, reason="Wrong quantity")
    good = w.invoice(po, "INF/0412", lines={LAPTOP: ("4", "1000")})
    assert good.status == "MATCHED"
    assert [i.status for i in po.invoices] == ["REJECTED", "MATCHED"]


def test_same_number_from_a_different_supplier_is_fine(w):
    po1, po2 = _received(w), _received(w, supplier=DIGITAL)
    w.invoice(po1, "0412", lines={LAPTOP: ("2", "1000")})
    assert w.invoice(po2, "0412", lines={LAPTOP: ("2", "1000")}).status == "MATCHED"


def test_database_index_backs_up_the_rule(w):
    po = _received(w)
    first = w.invoice(po, "INF/0412", lines={LAPTOP: ("2", "1000")})
    w.db.add(Invoice(supplier_invoice_number="INF/0412", po=po, supplier=po.supplier,
                     invoice_date=clock.today(), total=first.total, created_by=w.accounts.id))
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        w.db.flush()
