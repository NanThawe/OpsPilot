from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
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
from app.services.purchase_orders import (
    PurchaseOrderResponse,
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
    if (
        current_user.role != "admin"
        and document.created_by_id != current_user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if (
        document.status != "ready"
        or document.extraction_status != "completed"
    ):
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
        evidence_page_numbers=sorted(
            set(proposal.evidence_page_numbers)
        ),
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

    if (
        document is None
        or (
            current_user.role != "admin"
            and document.department_id != current_user.department_id
        )
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

    if (
        payload.decision == "reject"
        and not (payload.note or "").strip()
    ):
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
    if document is None or (
        user.role != "admin"
        and document.created_by_id != user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if (
        document.status != "ready"
        or document.extraction_status != "completed"
    ):
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

    db.add(record)
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