from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.api.classification import purchase_order_revision_response
from app.db.models import PurchaseOrderExtractionRevision


def test_revision_uses_composite_primary_key():
    columns = {
        column.name
        for column in (
            PurchaseOrderExtractionRevision
            .__table__
            .primary_key
            .columns
        )
    }

    assert columns == {
        "document_id",
        "revision_number",
    }


def test_revision_response_includes_actor_and_number():
    document_id = uuid4()
    user_id = uuid4()

    revision = SimpleNamespace(
        document_id=document_id,
        revision_number=2,
        extracted_data={"po_number": "PO-SYN-2026-003"},
        validation_report={
            "status": "flagged",
            "calculated_total": "1635.00",
            "issues": [],
        },
        model_name="ollama:qwen3:4b-instruct",
        created_by_id=user_id,
        created_at=datetime.now(UTC),
    )

    result = purchase_order_revision_response(revision)

    assert result["document_id"] == document_id
    assert result["revision_number"] == 2
    assert result["created_by_id"] == user_id
    assert result["validation"]["status"] == "flagged"