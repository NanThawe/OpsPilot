from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.classification import get_current_user, get_db
from app.api.knowledge import approved_knowledge_scope
from app.core.permissions import document_access_filter
from app.db.models import (
    AgentWorkflow,
    Document,
    DocumentChunk,
    DocumentClassification,
    PurchaseOrderExtraction,
    User,
)

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


class DashboardSummary(BaseModel):
    visible_documents: int
    pending_reviews: int
    flagged_purchase_orders: int
    pending_approvals: int
    ai_searchable_documents: int
    processing_issues: int


def _manager_role(user: User) -> bool:
    role = getattr(user.role, "value", user.role)
    return str(role).lower() in {"manager", "admin"}


@router.get(
    "/summary",
    response_model=DashboardSummary,
)
def dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> DashboardSummary:
    """Return permission-aware operational dashboard counts."""

    visible_document_ids = select(Document.id).where(
        document_access_filter(user)
    )

    visible_documents = db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.id.in_(visible_document_ids))
    ) or 0

    pending_reviews = db.scalar(
        select(
            func.count(
                func.distinct(
                    DocumentClassification.document_id
                )
            )
        ).where(
            DocumentClassification.document_id.in_(
                visible_document_ids
            ),
            DocumentClassification.review_status
            == "pending_review",
        )
    ) or 0

    flagged_purchase_orders = db.scalar(
        select(
            func.count(
                func.distinct(
                    PurchaseOrderExtraction.document_id
                )
            )
        ).where(
            PurchaseOrderExtraction.document_id.in_(
                visible_document_ids
            ),
            PurchaseOrderExtraction.validation_status.in_(
                ["flagged", "needs_review"]
            ),
        )
    ) or 0

    pending_workflow_query = select(
        func.count(
            func.distinct(AgentWorkflow.id)
        )
    ).where(
        AgentWorkflow.document_id.in_(
            visible_document_ids
        ),
        AgentWorkflow.status == "pending",
    )

    if not _manager_role(user):
        pending_workflow_query = (
            pending_workflow_query.where(
                AgentWorkflow.requested_by_id
                == user.id
            )
        )

    pending_approvals = (
        db.scalar(pending_workflow_query) or 0
    )

    ai_searchable_documents = db.scalar(
        select(
            func.count(
                func.distinct(
                    DocumentChunk.document_id
                )
            )
        )
        .select_from(DocumentChunk)
        .join(
            Document,
            DocumentChunk.document_id
            == Document.id,
        )
        .join(
            DocumentClassification,
            DocumentClassification.document_id
            == Document.id,
        )
        .where(
            approved_knowledge_scope(user),
        )
    ) or 0

    processing_issues = db.scalar(
        select(
            func.count(
                func.distinct(Document.id)
            )
        ).where(
            Document.id.in_(visible_document_ids),
            or_(
                Document.status == "failed",
                Document.extraction_status
                == "failed",
            ),
        )
    ) or 0

    return DashboardSummary(
        visible_documents=visible_documents,
        pending_reviews=pending_reviews,
        flagged_purchase_orders=(
            flagged_purchase_orders
        ),
        pending_approvals=pending_approvals,
        ai_searchable_documents=(
            ai_searchable_documents
        ),
        processing_issues=processing_issues,
    )
