from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import document_access_filter
from app.db.models import Document, DocumentPage, User
from app.db.session import get_db
from app.services.extraction import (
    ExtractionError,
    extract_pdf_pages,
)
from app.services.storage import (
    get_storage_path,
    verify_file_checksum,
)

router = APIRouter(
    prefix="/documents",
    tags=["Document Processing"],
)


class ExtractionResponse(BaseModel):
    document_id: UUID
    extraction_status: str
    page_count: int
    text_pages: int


class ExtractedPageResponse(BaseModel):
    page_number: int
    text: str
    source_ref: str


def record_extraction_failure(
    db: Session,
    document_id: UUID,
    message: str,
) -> None:
    db.rollback()

    document = db.get(Document, document_id)

    if document is not None:
        document.extraction_status = "failed"
        document.extraction_error = message[:500]
        document.page_count = None
        document.extracted_at = None

        db.commit()


@router.post(
    "/{document_id}/extract",
    response_model=ExtractionResponse,
)
def process_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    document = db.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # Only the document creator or an admin can process it.
    if current_user.role != "admin" and document.created_by_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if document.status != "ready" or not document.storage_key:
        raise HTTPException(
            status_code=409,
            detail="Document must be uploaded first",
        )

    if document.extraction_status not in {"pending", "failed"}:
        raise HTTPException(
            status_code=409,
            detail="Document is not awaiting extraction",
        )

    document.extraction_status = "processing"
    document.extraction_error = None
    db.commit()

    try:
        try:
            path = get_storage_path(document.storage_key)
        except ValueError as exc:
            raise ExtractionError("Invalid stored file reference") from exc

        if not path.is_file():
            raise ExtractionError("Stored PDF is missing")

        if not verify_file_checksum(path, document.sha256):
            raise ExtractionError("Stored PDF failed its integrity check")

        result = extract_pdf_pages(path)

        # Replace previous page records when retrying.
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))

        db.add_all(
            [
                DocumentPage(
                    document_id=document_id,
                    page_number=page_number,
                    text=text,
                )
                for page_number, text in result.pages
            ]
        )

        document.extraction_status = "completed" if result.pages else "needs_ocr"
        document.extraction_error = None
        document.page_count = result.page_count
        document.extracted_at = datetime.now(UTC)

        db.commit()

        return ExtractionResponse(
            document_id=document_id,
            extraction_status=document.extraction_status,
            page_count=result.page_count,
            text_pages=len(result.pages),
        )

    except ExtractionError as exc:
        record_extraction_failure(
            db,
            document_id,
            str(exc),
        )

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        record_extraction_failure(
            db,
            document_id,
            "Unexpected document processing failure",
        )
        raise


@router.get(
    "/{document_id}/pages",
    response_model=list[ExtractedPageResponse],
)
def get_document_pages(
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

    if document.extraction_status not in {
        "completed",
        "needs_ocr",
    }:
        raise HTTPException(
            status_code=409,
            detail="Document extraction is not complete",
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()

    return [
        ExtractedPageResponse(
            page_number=page.page_number,
            text=page.text,
            source_ref=(f"document:{document_id}:page:{page.page_number}"),
        )
        for page in pages
    ]
