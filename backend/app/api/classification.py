from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.permissions import document_access_filter
from app.db.models import (
    Document,
    DocumentClassification,
    DocumentPage,
    PurchaseOrderExtraction,
    PurchaseOrderExtractionRevision,
    PurchaseOrderReview,
    User,
)
from app.db.session import get_db
from app.services.classification import (
    ClassificationInputError,
    ClassificationServiceError,
    classification_model_name,
    classify_pages,
    validate_proposal,
)
from app.services.purchase_order_reviews import (
    PurchaseOrderReviewRequest,
    PurchaseOrderReviewResponse,
    can_approve_purchase_order,
    reviewer_can_review,
)
from app.services.purchase_orders import (
    PurchaseOrderResponse,
    PurchaseOrderRevisionResponse,
    PurchaseOrderServiceError,
    extract_purchase_order,
    validate_purchase_order,
)

router = APIRouter(
    prefix="/documents",
    tags=["AI Classification"],
)


class ClassificationResponse(BaseModel):
    document_id: UUID
    predicted_type: str
    confidence: str
    rationale: str
    evidence_page_numbers: list[int]
    model_name: str
    review_status: str
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    review_note: str | None

    model_config = ConfigDict(from_attributes=True)


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(
        default=None,
        max_length=500,
    )

    model_config = ConfigDict(extra="forbid")


@router.post(
    "/{document_id}/classify",
    response_model=ClassificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def classify_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # Only the creator or an admin can request classification.
    if current_user.role != "admin" and document.created_by_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if document.status != "ready" or document.extraction_status != "completed":
        raise HTTPException(
            status_code=409,
            detail="Document text extraction must be completed first",
        )

    if db.get(DocumentClassification, document_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Document already has a classification",
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()

    if not pages:
        raise HTTPException(
            status_code=409,
            detail="No extracted text is available",
        )

    try:
        proposal = classify_pages(pages)
        validate_proposal(proposal, pages)

    except ClassificationInputError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except ClassificationServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    classification = DocumentClassification(
        document_id=document_id,
        predicted_type=proposal.predicted_type,
        confidence=proposal.confidence,
        rationale=proposal.rationale,
        evidence_page_numbers=sorted(set(proposal.evidence_page_numbers)),
        model_name=classification_model_name(),
        review_status="pending_review",
    )

    db.add(classification)

    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Document classification already exists",
        ) from exc

    db.refresh(classification)

    return classification


@router.get(
    "/{document_id}/classification",
    response_model=ClassificationResponse,
)
def get_classification(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            document_access_filter(current_user),
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    classification = db.get(
        DocumentClassification,
        document_id,
    )

    if classification is None:
        raise HTTPException(
            status_code=404,
            detail="Classification not found",
        )

    return classification


@router.post(
    "/{document_id}/classification/review",
    response_model=ClassificationResponse,
)
def review_classification(
    document_id: UUID,
    payload: ReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if current_user.role not in {"manager", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Reviewer permissions required",
        )

    document = db.get(Document, document_id)

    if document is None or (
        current_user.role != "admin"
        and document.department_id != current_user.department_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    classification = db.scalar(
        select(DocumentClassification)
        .where(DocumentClassification.document_id == document_id)
        .with_for_update()
    )

    if classification is None:
        raise HTTPException(
            status_code=404,
            detail="Classification not found",
        )

    if classification.review_status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="Classification has already been reviewed",
        )

    if payload.decision == "reject" and not (payload.note or "").strip():
        raise HTTPException(
            status_code=422,
            detail="A reason is required when rejecting",
        )

    classification.review_status = (
        "approved" if payload.decision == "approve" else "rejected"
    )

    classification.reviewed_by_id = current_user.id
    classification.reviewed_at = datetime.now(UTC)
    classification.review_note = payload.note

    db.commit()
    db.refresh(classification)

    return classification


def purchase_order_response(
    record: PurchaseOrderExtraction,
) -> dict:
    return {
        "document_id": record.document_id,
        "extraction": record.extracted_data,
        "validation": record.validation_report,
        "model_name": record.model_name,
        "created_at": record.created_at,
    }


@router.post(
    "/{document_id}/purchase-order/extract",
    response_model=PurchaseOrderResponse,
    status_code=201,
    tags=["Purchase Orders"],
)
def extract_purchase_order_endpoint(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = db.get(Document, document_id)

    # Only the document creator or an admin may initiate extraction.
    # Return 404 to avoid revealing inaccessible document IDs.
    if document is None or (user.role != "admin" and document.created_by_id != user.id):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if document.status != "ready" or document.extraction_status != "completed":
        raise HTTPException(
            status_code=409,
            detail="PDF text extraction must be completed first",
        )

    classification = db.get(
        DocumentClassification,
        document_id,
    )

    if (
        classification is None
        or classification.predicted_type != "purchase_order"
        or classification.review_status != "approved"
    ):
        raise HTTPException(
            status_code=409,
            detail="An approved purchase order classification is required",
        )

    existing = db.get(PurchaseOrderExtraction, document_id)

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Purchase order extraction already exists",
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()

    if not pages:
        raise HTTPException(
            status_code=409,
            detail="No extracted PDF pages found",
        )

    try:
        proposal = extract_purchase_order(pages)
    except PurchaseOrderServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    validation = validate_purchase_order(proposal)

    record = PurchaseOrderExtraction(
        document_id=document_id,
        extracted_data=proposal.model_dump(),
        validation_report=validation.model_dump(),
        validation_status=validation.status,
        model_name=f"ollama:{settings.ollama_model}",
    )

    first_revision = PurchaseOrderExtractionRevision(
        document_id=document_id,
        revision_number=1,
        extracted_data=proposal.model_dump(),
        validation_report=validation.model_dump(),
        validation_status=validation.status,
        model_name=f"ollama:{settings.ollama_model}",
        created_by_id=user.id,
    )

    db.add_all([record, first_revision])
    db.commit()
    db.refresh(record)

    return purchase_order_response(record)


@router.get(
    "/{document_id}/purchase-order",
    response_model=PurchaseOrderResponse,
    tags=["Purchase Orders"],
)
def get_purchase_order_endpoint(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            document_access_filter(user),
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    record = db.get(PurchaseOrderExtraction, document_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Purchase order extraction not found",
        )

    return purchase_order_response(record)


def purchase_order_revision_response(
    revision: PurchaseOrderExtractionRevision,
) -> dict:
    return {
        "document_id": revision.document_id,
        "extraction": revision.extracted_data,
        "validation": revision.validation_report,
        "model_name": revision.model_name,
        "created_at": revision.created_at,
        "revision_number": revision.revision_number,
        "created_by_id": revision.created_by_id,
    }


@router.post(
    "/{document_id}/purchase-order/reprocess",
    response_model=PurchaseOrderRevisionResponse,
    status_code=201,
    tags=["Purchase Orders"],
)
def reprocess_purchase_order_endpoint(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = db.get(Document, document_id)

    if document is None or (user.role != "admin" and document.created_by_id != user.id):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if document.status != "ready" or document.extraction_status != "completed":
        raise HTTPException(
            status_code=409,
            detail="PDF text extraction must be completed first",
        )

    classification = db.get(
        DocumentClassification,
        document_id,
    )

    if (
        classification is None
        or classification.predicted_type != "purchase_order"
        or classification.review_status != "approved"
    ):
        raise HTTPException(
            status_code=409,
            detail="Approved purchase order classification required",
        )

    existing = db.get(PurchaseOrderExtraction, document_id)

    if existing is None:
        raise HTTPException(
            status_code=409,
            detail="No existing extraction. Use the extract endpoint first",
        )

    if existing.validation_status not in {"needs_review", "flagged"}:
        raise HTTPException(
            status_code=409,
            detail="Only incomplete or flagged extractions can be retried",
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()

    if not pages:
        raise HTTPException(
            status_code=409,
            detail="No extracted document pages found",
        )

    try:
        proposal = extract_purchase_order(pages)
    except PurchaseOrderServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    validation = validate_purchase_order(proposal)

    # Acquire the row lock only after the Ollama request finishes.
    current = db.scalar(
        select(PurchaseOrderExtraction)
        .where(PurchaseOrderExtraction.document_id == document_id)
        .with_for_update()
    )

    if current is None or current.validation_status not in {
        "needs_review",
        "flagged",
    }:
        raise HTTPException(
            status_code=409,
            detail="Extraction is no longer eligible for reprocessing",
        )

    latest_number = db.scalar(
        select(func.max(PurchaseOrderExtractionRevision.revision_number)).where(
            PurchaseOrderExtractionRevision.document_id == document_id
        )
    )

    existing_decision = db.get(
        PurchaseOrderReview,
        (document_id, latest_number or 1),
    )

    if existing_decision is not None and existing_decision.decision in {
        "approved",
        "rejected",
    }:
        raise HTTPException(
            status_code=409,
            detail="Approved or rejected revisions cannot be reprocessed",
        )

    if latest_number is None:
        # Preserve an extraction created before revision tracking existed.
        original_revision = PurchaseOrderExtractionRevision(
            document_id=document_id,
            revision_number=1,
            extracted_data=current.extracted_data,
            validation_report=current.validation_report,
            validation_status=current.validation_status,
            model_name=current.model_name,
            created_by_id=None,
            created_at=current.created_at,
        )

        db.add(original_revision)
        latest_number = 1

    new_revision = PurchaseOrderExtractionRevision(
        document_id=document_id,
        revision_number=latest_number + 1,
        extracted_data=proposal.model_dump(),
        validation_report=validation.model_dump(),
        validation_status=validation.status,
        model_name=f"ollama:{settings.ollama_model}",
        created_by_id=user.id,
    )

    db.add(new_revision)

    # Replace the latest-result fields, not the historical revision.
    current.extracted_data = proposal.model_dump()
    current.validation_report = validation.model_dump()
    current.validation_status = validation.status
    current.model_name = f"ollama:{settings.ollama_model}"

    db.commit()
    db.refresh(new_revision)

    return purchase_order_revision_response(new_revision)


@router.get(
    "/{document_id}/purchase-order/history",
    response_model=list[PurchaseOrderRevisionResponse],
    tags=["Purchase Orders"],
)
def get_purchase_order_history_endpoint(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            document_access_filter(user),
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    revisions = db.scalars(
        select(PurchaseOrderExtractionRevision)
        .where(PurchaseOrderExtractionRevision.document_id == document_id)
        .order_by(PurchaseOrderExtractionRevision.revision_number)
    ).all()

    if revisions:
        return [purchase_order_revision_response(revision) for revision in revisions]

    # Compatibility for records created before Step 12.
    existing = db.get(PurchaseOrderExtraction, document_id)

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail="Purchase order extraction not found",
        )

    return [
        {
            "document_id": existing.document_id,
            "extraction": existing.extracted_data,
            "validation": existing.validation_report,
            "model_name": existing.model_name,
            "created_at": existing.created_at,
            "revision_number": 1,
            "created_by_id": None,
        }
    ]


@router.post(
    "/{document_id}/purchase-order/review",
    response_model=PurchaseOrderReviewResponse,
    status_code=201,
    tags=["Purchase Order Reviews"],
)
def review_purchase_order_endpoint(
    document_id: UUID,
    payload: PurchaseOrderReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if not reviewer_can_review(
        user.role,
        user.department_id,
        document.department_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="You cannot review this department's purchase orders",
        )

    if user.id == document.created_by_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot review your own purchase order",
        )

    # Lock the current extraction while deciding.
    current = db.scalar(
        select(PurchaseOrderExtraction)
        .where(PurchaseOrderExtraction.document_id == document_id)
        .with_for_update()
    )

    if current is None:
        raise HTTPException(
            status_code=409,
            detail="Purchase order has not been extracted",
        )

    latest_revision = (
        db.scalar(
            select(func.max(PurchaseOrderExtractionRevision.revision_number)).where(
                PurchaseOrderExtractionRevision.document_id == document_id
            )
        )
        or 1
    )

    if payload.revision_number != latest_revision:
        raise HTTPException(
            status_code=409,
            detail="This is not the latest extraction revision",
        )

    revision = db.get(
        PurchaseOrderExtractionRevision,
        (document_id, latest_revision),
    )

    if revision is not None and revision.created_by_id == user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot review an extraction you initiated",
        )

    existing_review = db.get(
        PurchaseOrderReview,
        (document_id, latest_revision),
    )

    if existing_review is not None:
        raise HTTPException(
            status_code=409,
            detail="This revision has already been reviewed",
        )

    if payload.decision == "approve" and not can_approve_purchase_order(
        current.validation_status
    ):
        raise HTTPException(
            status_code=409,
            detail="Only purchase orders with passed validation can be approved",
        )

    decisions = {
        "approve": "approved",
        "reject": "rejected",
        "request_changes": "changes_requested",
    }

    review = PurchaseOrderReview(
        document_id=document_id,
        revision_number=latest_revision,
        decision=decisions[payload.decision],
        note=payload.note,
        reviewed_by_id=user.id,
    )

    db.add(review)
    db.commit()
    db.refresh(review)

    return review


@router.get(
    "/{document_id}/purchase-order/reviews",
    response_model=list[PurchaseOrderReviewResponse],
    tags=["Purchase Order Reviews"],
)
def get_purchase_order_reviews_endpoint(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            document_access_filter(user),
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return db.scalars(
        select(PurchaseOrderReview)
        .where(PurchaseOrderReview.document_id == document_id)
        .order_by(PurchaseOrderReview.revision_number)
    ).all()
