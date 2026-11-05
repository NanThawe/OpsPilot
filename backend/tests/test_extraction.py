import hashlib
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.base import Base
from app.db.models import Department, Document, User
from app.db.session import get_db
from app.main import app


def make_text_pdf():
    output = BytesIO()
    pdf = canvas.Canvas(output)

    pdf.drawString(72, 750, "Invoice INV-1001")
    pdf.showPage()

    pdf.drawString(72, 750, "Purchase Order PO-2026-002")
    pdf.save()

    return output.getvalue()


def make_blank_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    output = BytesIO()
    writer.write(output)

    return output.getvalue()


@pytest.fixture
def context(tmp_path, monkeypatch):
    storage_dir = tmp_path / "private_documents"
    storage_dir.mkdir()

    monkeypatch.setattr(
        settings,
        "document_storage_dir",
        storage_dir,
    )

    pdf_bytes = make_text_pdf()
    storage_key = f"{uuid4().hex}.pdf"
    file_path = storage_dir / storage_key

    file_path.write_bytes(pdf_bytes)

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
            title="Test Procurement Document",
            original_filename="test-document.pdf",
            department_id=finance.id,
            created_by_id=finance_user.id,
            visibility="department",
            status="ready",
            storage_key=storage_key,
            sha256=hashlib.sha256(pdf_bytes).hexdigest(),
            size_bytes=len(pdf_bytes),
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
            engine=engine,
            file_path=file_path,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def extract(context):
    return context.client.post(f"/documents/{context.document.id}/extract")


def get_pages(context):
    return context.client.get(f"/documents/{context.document.id}/pages")


def test_extracts_text_with_page_references(context):
    context.login_as(context.finance_user)

    response = extract(context)

    assert response.status_code == 200

    data = response.json()

    assert data["extraction_status"] == "completed"
    assert data["page_count"] == 2
    assert data["text_pages"] == 2

    pages_response = get_pages(context)

    assert pages_response.status_code == 200

    pages = pages_response.json()

    assert len(pages) == 2
    assert "Invoice INV-1001" in pages[0]["text"]
    assert "Purchase Order PO-2026-002" in pages[1]["text"]
    assert pages[0]["page_number"] == 1
    assert pages[1]["page_number"] == 2
    assert pages[0]["source_ref"].endswith(":page:1")


def test_other_department_cannot_extract(context):
    context.login_as(context.operations_user)

    response = extract(context)

    assert response.status_code == 404


def test_other_department_cannot_read_pages(context):
    context.login_as(context.finance_user)

    assert extract(context).status_code == 200

    context.login_as(context.operations_user)

    response = get_pages(context)

    assert response.status_code == 404


def test_cannot_extract_completed_document_again(context):
    context.login_as(context.finance_user)

    first = extract(context)
    second = extract(context)

    assert first.status_code == 200
    assert second.status_code == 409


def test_blank_pdf_requires_ocr(context):
    blank_pdf = make_blank_pdf()

    context.file_path.write_bytes(blank_pdf)

    with Session(context.engine) as db:
        document = db.get(Document, context.document.id)
        document.sha256 = hashlib.sha256(blank_pdf).hexdigest()
        document.size_bytes = len(blank_pdf)
        db.commit()

    context.login_as(context.finance_user)

    response = extract(context)

    assert response.status_code == 200
    assert response.json()["extraction_status"] == "needs_ocr"
    assert response.json()["page_count"] == 1
    assert response.json()["text_pages"] == 0

    assert get_pages(context).json() == []


def test_checksum_failure_is_recorded(context):
    context.file_path.write_bytes(b"modified file")

    context.login_as(context.finance_user)

    response = extract(context)

    assert response.status_code == 422

    with Session(context.engine) as db:
        document = db.get(Document, context.document.id)

        assert document.extraction_status == "failed"
        assert document.extraction_error is not None


def test_document_must_be_uploaded_first(context):
    with Session(context.engine) as db:
        document = db.get(Document, context.document.id)
        document.status = "pending_upload"
        db.commit()

    context.login_as(context.finance_user)

    response = extract(context)

    assert response.status_code == 409


def test_pages_are_unavailable_before_extraction(context):
    context.login_as(context.finance_user)

    response = get_pages(context)

    assert response.status_code == 409
