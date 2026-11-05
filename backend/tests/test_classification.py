from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.classification as classification_api
from app.core.dependencies import get_current_user
from app.db.base import Base
from app.db.models import (
    Department,
    Document,
    DocumentClassification,
    DocumentPage,
    User,
)
from app.db.session import get_db
from app.main import app
from app.services.classification import (
    ClassificationProposal,
    validate_proposal,
)


@pytest.fixture
def context(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as db:
        operations = Department(name="Operations")
        finance = Department(name="Finance")
        it = Department(name="IT")

        db.add_all([operations, finance, it])
        db.flush()

        operations_user = User(
            email="operations@test.local",
            role="staff",
            department_id=operations.id,
            password_hash="test-only",
        )

        finance_user = User(
            email="finance@test.local",
            role="staff",
            department_id=finance.id,
            password_hash="test-only",
        )

        operations_manager = User(
            email="manager@test.local",
            role="manager",
            department_id=operations.id,
            password_hash="test-only",
        )

        admin_user = User(
            email="admin@test.local",
            role="admin",
            department_id=it.id,
            password_hash="test-only",
        )

        db.add_all(
            [
                operations_user,
                finance_user,
                operations_manager,
                admin_user,
            ]
        )
        db.flush()

        document = Document(
            title="Synthetic Purchase Order",
            original_filename="po.pdf",
            department_id=operations.id,
            created_by_id=operations_user.id,
            visibility="department",
            status="ready",
            extraction_status="completed",
        )

        db.add(document)
        db.flush()

        db.add(
            DocumentPage(
                document_id=document.id,
                page_number=1,
                text=(
                    "PURCHASE ORDER PO-SYN-2026-001. "
                    "Supplier: Cedarline Office Systems. "
                    "Ordered goods, quantities, prices and delivery date."
                ),
            )
        )

        db.commit()

    def override_db():
        with Session(engine) as db:
            yield db

    def login_as(user):
        app.dependency_overrides[get_current_user] = lambda: user

    def fake_classify(_pages):
        return ClassificationProposal(
            predicted_type="purchase_order",
            confidence="high",
            rationale="The document orders goods from a supplier.",
            evidence_page_numbers=[1],
        )

    monkeypatch.setattr(
        classification_api,
        "classify_pages",
        fake_classify,
    )

    app.dependency_overrides[get_db] = override_db

    try:
        yield SimpleNamespace(
            client=TestClient(app),
            login_as=login_as,
            operations_user=operations_user,
            finance_user=finance_user,
            operations_manager=operations_manager,
            admin_user=admin_user,
            document=document,
            engine=engine,
        )

    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def classify(context):
    return context.client.post(f"/documents/{context.document.id}/classify")


def review(context, decision="approve", note=None):
    return context.client.post(
        f"/documents/{context.document.id}/classification/review",
        json={
            "decision": decision,
            "note": note,
        },
    )


def test_staff_creates_pending_review(context):
    context.login_as(context.operations_user)

    response = classify(context)

    assert response.status_code == 201

    data = response.json()

    assert data["predicted_type"] == "purchase_order"
    assert data["confidence"] == "high"
    assert data["review_status"] == "pending_review"
    assert data["evidence_page_numbers"] == [1]


def test_other_department_cannot_classify(context):
    context.login_as(context.finance_user)

    response = classify(context)

    assert response.status_code == 404


def test_extraction_is_required(context):
    with Session(context.engine) as db:
        document = db.get(Document, context.document.id)
        document.extraction_status = "pending"
        db.commit()

    context.login_as(context.operations_user)

    assert classify(context).status_code == 409


def test_document_cannot_be_classified_twice(context):
    context.login_as(context.operations_user)

    assert classify(context).status_code == 201
    assert classify(context).status_code == 409


def test_staff_cannot_approve(context):
    context.login_as(context.operations_user)

    classify(context)

    response = review(context)

    assert response.status_code == 403


def test_admin_can_approve(context):
    context.login_as(context.operations_user)

    assert classify(context).status_code == 201

    context.login_as(context.admin_user)

    response = review(
        context,
        note="Reviewed against the purchase order.",
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"
    assert response.json()["reviewed_by_id"] == str(context.admin_user.id)


def test_manager_can_approve_own_department(context):
    context.login_as(context.operations_user)

    assert classify(context).status_code == 201

    context.login_as(context.operations_manager)

    response = review(context)

    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"


def test_other_department_cannot_read_classification(context):
    context.login_as(context.operations_user)

    assert classify(context).status_code == 201

    context.login_as(context.finance_user)

    response = context.client.get(f"/documents/{context.document.id}/classification")

    assert response.status_code == 404


def test_invalid_ai_evidence_is_not_saved(context, monkeypatch):
    def invalid_classification(_pages):
        return ClassificationProposal(
            predicted_type="purchase_order",
            confidence="high",
            rationale="This is a purchase order.",
            evidence_page_numbers=[99],
        )

    monkeypatch.setattr(
        classification_api,
        "classify_pages",
        invalid_classification,
    )

    context.login_as(context.operations_user)

    response = classify(context)

    assert response.status_code == 503

    with Session(context.engine) as db:
        assert (
            db.get(
                DocumentClassification,
                context.document.id,
            )
            is None
        )


def test_long_rationale_is_trimmed():
    proposal = ClassificationProposal(
        predicted_type="purchase_order",
        confidence="high",
        rationale="This is a purchase order. " * 30,
        evidence_page_numbers=[1],
    )

    pages = [SimpleNamespace(page_number=1)]

    validate_proposal(proposal, pages)

    assert len(proposal.rationale) <= 500
    assert proposal.rationale.endswith("...")
