"""Document numbers: PR-0001, PO-0001, GRN-0001 (D-31).

The counter is bumped with a single upsert inside the caller's transaction. SQLite takes the
write lock on that statement, so concurrent requests serialise, and a rollback returns the
number — sequences stay gap-free.
"""

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models.enums import DocumentType
from app.models.sequence import DocumentSequence


def format_number(doc_type: DocumentType, value: int) -> str:
    return f"{doc_type.value}-{value:04d}"


def next_number(db: Session, doc_type: DocumentType) -> str:
    stmt = (
        insert(DocumentSequence)
        .values(doc_type=doc_type, last_value=1)
        .on_conflict_do_update(
            index_elements=[DocumentSequence.doc_type],
            set_={"last_value": DocumentSequence.last_value + 1},
        )
        .returning(DocumentSequence.last_value)
    )
    value = db.execute(stmt).scalar_one()
    return format_number(doc_type, value)
