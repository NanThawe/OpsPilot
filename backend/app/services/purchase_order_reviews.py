from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PurchaseOrderReviewRequest(BaseModel):
    revision_number: int = Field(ge=1)

    decision: Literal[
        "approve",
        "reject",
        "request_changes",
    ]

    note: str | None = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_review_note(self):
        if self.note is not None:
            self.note = self.note.strip()

        if self.decision in {
            "reject",
            "request_changes",
        } and not self.note:
            raise ValueError(
                "A review note is required for rejection "
                "or change requests"
            )

        return self


class PurchaseOrderReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_id: UUID
    revision_number: int
    decision: Literal[
        "approved",
        "rejected",
        "changes_requested",
    ]
    note: str | None
    reviewed_by_id: UUID
    reviewed_at: datetime


def reviewer_can_review(
    role: str,
    user_department_id: UUID | None,
    document_department_id: UUID | None,
) -> bool:
    if role == "admin":
        return True

    return (
        role == "manager"
        and user_department_id is not None
        and user_department_id == document_department_id
    )


def can_approve_purchase_order(
    validation_status: str,
) -> bool:
    return validation_status == "passed"