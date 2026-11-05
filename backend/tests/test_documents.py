from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.db.base import Base
from app.db.models import Department, Document, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as db:
        finance = Department(name="Finance")
        operations = Department(name="Operations")
        it = Department(name="IT")

        db.add_all([finance, operations, it])
        db.flush()

        finance_user = User(
            email="finance@test.local",
            role="staff",
            department_id=finance.id,
            password_hash="test-only",
        )

        operations_user = User(
            email="operations@test.local",
            role="staff",
            department_id=operations.id,
            password_hash="test-only",
        )

        admin_user = User(
            email="admin@test.local",
            role="admin",
            department_id=it.id,
            password_hash="test-only",
        )

        db.add_all([finance_user, operations_user, admin_user])
        db.flush()

        finance_doc = Document(
            title="Finance Invoice",
            original_filename="invoice.pdf",
            department_id=finance.id,
            created_by_id=finance_user.id,
            visibility="department",
        )

        operations_doc = Document(
            title="Operations Delivery Order",
            original_filename="delivery.pdf",
            department_id=operations.id,
            created_by_id=operations_user.id,
            visibility="department",
        )

        company_doc = Document(
            title="Company Handbook",
            original_filename="handbook.pdf",
            department_id=it.id,
            created_by_id=admin_user.id,
            visibility="company",
        )

        db.add_all([finance_doc, operations_doc, company_doc])
        db.commit()

    def override_db():
        with Session(engine) as db:
            yield db

    def login_as(user):
        app.dependency_overrides[get_current_user] = lambda: user

    app.dependency_overrides[get_db] = override_db

    try:
        yield SimpleNamespace(
            client=TestClient(app),
            login_as=login_as,
            finance_user=finance_user,
            admin_user=admin_user,
            finance_doc=finance_doc,
            operations_doc=operations_doc,
            company_doc=company_doc,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_documents_require_login(context):
    response = context.client.get("/documents")

    assert response.status_code == 401


def test_staff_only_lists_accessible_documents(context):
    context.login_as(context.finance_user)

    response = context.client.get("/documents")

    assert response.status_code == 200

    returned_ids = {item["id"] for item in response.json()}

    assert str(context.finance_doc.id) in returned_ids
    assert str(context.company_doc.id) in returned_ids
    assert str(context.operations_doc.id) not in returned_ids


def test_staff_cannot_read_other_department_document(context):
    context.login_as(context.finance_user)

    response = context.client.get(f"/documents/{context.operations_doc.id}")

    assert response.status_code == 404


def test_staff_can_register_department_document(context):
    context.login_as(context.finance_user)

    response = context.client.post(
        "/documents",
        json={
            "title": "New Purchase Order",
            "original_filename": "po-001.pdf",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["visibility"] == "department"
    assert data["status"] == "pending_upload"
    assert data["department_id"] == str(context.finance_user.department_id)


def test_staff_cannot_publish_company_document(context):
    context.login_as(context.finance_user)

    response = context.client.post(
        "/documents",
        json={
            "title": "Restricted Document",
            "original_filename": "restricted.pdf",
            "visibility": "company",
        },
    )

    assert response.status_code == 403


def test_admin_can_see_all_documents(context):
    context.login_as(context.admin_user)

    response = context.client.get("/documents")

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_admin_can_register_company_document(context):
    context.login_as(context.admin_user)

    response = context.client.post(
        "/documents",
        json={
            "title": "New Company Policy",
            "original_filename": "policy.pdf",
            "visibility": "company",
        },
    )

    assert response.status_code == 201
    assert response.json()["visibility"] == "company"
