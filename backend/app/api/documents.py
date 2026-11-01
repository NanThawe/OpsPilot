from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import document_access_filter
from app.db.models import Document, User
from app.db.session import get_db
from app.services.storage import (
    FileTooLargeError,
    InvalidPdfError,
    get_storage_path,
    save_pdf,
    verify_file_checksum,
)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    original_filename: str = Field(min_length=1, max_length=255)
    visibility: Literal["department", "company"] = "department"

    model_config = ConfigDict(extra="forbid")


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    original_filename: str
    department_id: UUID
    created_by_id: UUID
    visibility: str
    status: str
    created_at: datetime
    size_bytes: int | None
    sha256: str | None

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_document(
    payload: DocumentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if (
        payload.visibility == "company"
        and current_user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create company-wide documents",
        )

    document = Document(
        title=payload.title,
        original_filename=payload.original_filename,
        department_id=current_user.department_id,
        created_by_id=current_user.id,
        visibility=payload.visibility,
        status="pending_upload",
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


@router.get(
    "",
    response_model=list[DocumentResponse],
)
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    statement = (
        select(Document)
        .where(document_access_filter(current_user))
        .order_by(Document.created_at.desc(), Document.id)
        .offset(offset)
        .limit(limit)
    )

    return db.scalars(statement).all()


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    statement = select(Document).where(
        Document.id == document_id,
        document_access_filter(current_user),
    )

    document = db.scalar(statement)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document

@router.post(
    "/{document_id}/upload",
    response_model=DocumentResponse,
)
def upload_document(
    document_id: UUID,
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    document = db.scalar(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # Only the creator or an administrator can upload.
    if (
        current_user.role != "admin"
        and document.created_by_id != current_user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # Prevent replacing an existing uploaded file.
    if document.status != "pending_upload" or document.storage_key:
        raise HTTPException(
            status_code=409,
            detail="Document is not awaiting upload",
        )

    if file.filename != document.original_filename:
        raise HTTPException(
            status_code=422,
            detail="Filename must match the registered document",
        )

    try:
        storage_key, sha256, size_bytes = save_pdf(file)

    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc

    except InvalidPdfError as exc:
        raise HTTPException(
            status_code=415,
            detail=str(exc),
        ) from exc

    document.storage_key = storage_key
    document.sha256 = sha256
    document.size_bytes = size_bytes
    document.status = "ready"

    try:
        db.commit()

    except Exception:
        db.rollback()

        # Remove the stored file if database commit fails.
        get_storage_path(storage_key).unlink(missing_ok=True)
        raise

    db.refresh(document)

    return document

@router.get("/{document_id}/download")
def download_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    statement = select(Document).where(
        Document.id == document_id,
        document_access_filter(current_user),
    )

    document = db.scalar(statement)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if document.status != "ready" or not document.storage_key:
        raise HTTPException(
            status_code=409,
            detail="Document is not ready for download",
        )

    try:
        path = get_storage_path(document.storage_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="Invalid stored file reference",
        ) from exc

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored file is missing",
        )

    if not verify_file_checksum(path, document.sha256):
        raise HTTPException(
            status_code=409,
            detail="File integrity verification failed",
        )

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=document.original_filename,
        content_disposition_type="attachment",
    )