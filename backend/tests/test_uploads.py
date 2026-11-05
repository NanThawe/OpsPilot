import hashlib
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.base import Base
from app.db.models import Department, Document, User
from app.db.session import get_db
from app.main import app


def make_test_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    output = BytesIO()
    writer.write(output)

    return output.getvalue()


@pytest.fixture
def context(tmp_path, monkeypatch):
    storage_dir = tmp_path / "private_documents"

    monkeypatch.setattr(
        settings,
        "document_storage_dir",
        storage_dir,
    )

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as db:
        finance = Department(name="Finance")
        operations = Department(name="Operations")

        db.add_all([finance, operations])
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

        db.add_all([finance_user, operations_user])
        db.flush()

        document = Document(
            title="Purchase Order",
            original_filename="purchase-order.pdf",
            department_id=finance.id,
            created_by_id=finance_user.id,
            visibility="department",
        )

        db.add(document)
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
            operations_user=operations_user,
            document=document,
            storage_dir=storage_dir,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def upload_file(context, contents, filename="purchase-order.pdf"):
    return context.client.post(
        f"/documents/{context.document.id}/upload",
        files={
            "file": (
                filename,
                contents,
                "application/pdf",
            )
        },
    )


def test_upload_requires_login(context):
    response = upload_file(context, make_test_pdf())

    assert response.status_code == 401


def test_valid_pdf_upload_and_download(context):
    context.login_as(context.finance_user)

    pdf_bytes = make_test_pdf()

    response = upload_file(context, pdf_bytes)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ready"
    assert data["size_bytes"] == len(pdf_bytes)
    assert data["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()

    download = context.client.get(f"/documents/{context.document.id}/download")

    assert download.status_code == 200
    assert download.content == pdf_bytes


def test_other_department_cannot_upload(context):
    context.login_as(context.operations_user)

    response = upload_file(context, make_test_pdf())

    assert response.status_code == 404


def test_other_department_cannot_download(context):
    context.login_as(context.finance_user)

    upload_file(context, make_test_pdf())

    context.login_as(context.operations_user)

    response = context.client.get(f"/documents/{context.document.id}/download")

    assert response.status_code == 404


def test_oversized_pdf_is_rejected(context):
    context.login_as(context.finance_user)

    oversized_data = make_test_pdf() + (b"x" * (10 * 1024 * 1024))

    response = upload_file(context, oversized_data)

    assert response.status_code == 413
    assert not list(context.storage_dir.iterdir())


def test_invalid_pdf_is_rejected(context):
    context.login_as(context.finance_user)

    response = upload_file(
        context,
        b"This is not a PDF document",
    )

    assert response.status_code == 415
    assert not list(context.storage_dir.iterdir())


def test_filename_must_match_registration(context):
    context.login_as(context.finance_user)

    response = upload_file(
        context,
        make_test_pdf(),
        filename="different.pdf",
    )

    assert response.status_code == 422


def test_document_cannot_be_uploaded_twice(context):
    context.login_as(context.finance_user)

    first = upload_file(context, make_test_pdf())
    second = upload_file(context, make_test_pdf())

    assert first.status_code == 200
    assert second.status_code == 409


def test_modified_stored_file_fails_integrity_check(context):
    context.login_as(context.finance_user)

    response = upload_file(context, make_test_pdf())

    assert response.status_code == 200

    stored_file = next(context.storage_dir.glob("*.pdf"))

    stored_file.write_bytes(b"modified after upload")

    download = context.client.get(f"/documents/{context.document.id}/download")

    assert download.status_code == 409
