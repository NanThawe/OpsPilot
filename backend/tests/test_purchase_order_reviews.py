from uuid import uuid4

import pytest
from app.services.purchase_order_reviews import (
    PurchaseOrderReviewRequest,
    can_approve_purchase_order,
    reviewer_can_review,
)
from pydantic import ValidationError


def test_only_passed_orders_can_be_approved():
    assert can_approve_purchase_order("passed")
    assert not can_approve_purchase_order("flagged")
    assert not can_approve_purchase_order("needs_review")


def test_change_request_requires_note():
    with pytest.raises(ValidationError):
        PurchaseOrderReviewRequest(
            revision_number=2,
            decision="request_changes",
            note="",
        )


def test_rejection_requires_note():
    with pytest.raises(ValidationError):
        PurchaseOrderReviewRequest(
            revision_number=2,
            decision="reject",
        )


def test_manager_can_review_own_department():
    department_id = uuid4()

    assert reviewer_can_review(
        "manager",
        department_id,
        department_id,
    )


def test_manager_cannot_review_other_department():
    assert not reviewer_can_review(
        "manager",
        uuid4(),
        uuid4(),
    )


def test_staff_cannot_review():
    department_id = uuid4()

    assert not reviewer_can_review(
        "staff",
        department_id,
        department_id,
    )


def test_admin_can_review_other_department():
    assert reviewer_can_review(
        "admin",
        uuid4(),
        uuid4(),
    )