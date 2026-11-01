from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import document_access_filter
from app.db.models import Document, User
from app.db.session import get_db

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