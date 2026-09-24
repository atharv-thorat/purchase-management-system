"""Document numbers from the counter table (D-31)."""

import pytest

from app.core.errors import BusinessRuleViolation
from app.models.enums import DocumentType
from app.services.numbering import format_number, next_number
from tests.conftest import LARGE


def test_format_pads_to_four_digits_and_grows_beyond():
    assert format_number(DocumentType.PR, 1) == "PR-0001"
    assert format_number(DocumentType.GRN, 12345) == "GRN-12345"


def test_each_document_type_has_its_own_sequence(db):
    assert [next_number(db, DocumentType.PR) for _ in range(3)] == ["PR-0001", "PR-0002", "PR-0003"]
    assert next_number(db, DocumentType.PO) == "PO-0001"
    assert next_number(db, DocumentType.GRN) == "GRN-0001"
    assert next_number(db, DocumentType.PR) == "PR-0004"


def test_rolled_back_transaction_gives_the_number_back(db):
    next_number(db, DocumentType.PR)
    db.commit()
    assert next_number(db, DocumentType.PR) == "PR-0002"
    db.rollback()
    assert next_number(db, DocumentType.PR) == "PR-0002"


def test_prs_get_numbers_at_creation(w):
    assert [w.draft().pr_number, w.draft().pr_number] == ["PR-0001", "PR-0002"]


def test_failed_action_does_not_consume_a_number(w):
    with pytest.raises(BusinessRuleViolation):
        w.draft(lines=[])
    assert w.draft().pr_number == "PR-0001"


def test_po_and_grn_numbers_follow_creation_order(w):
    po1 = w.po()
    po2 = w.po(lines=LARGE)
    grn1 = w.receive(po2)
    grn2 = w.receive(po1)
    assert (po1.po_number, po2.po_number, grn1.grn_number, grn2.grn_number) == \
        ("PO-0001", "PO-0002", "GRN-0001", "GRN-0002")
