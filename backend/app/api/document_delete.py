from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.classification import get_current_user, get_db
from app.core.permissions import document_access_filter
from app.db.models import Document, User
from app.services.document_delete import (
    DocumentDeleteConflict,
    DocumentDeleteForbidden,
    delete_document_record,
)

router = APIRouter(tags=["Documents"])


@router.delete(
    "/documents/{document_id}",
    status_code=204,
)
def delete_document(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            document_access_filter(user),
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    try:
        delete_document_record(
            db,
            document=document,
            user=user,
        )
    except DocumentDeleteForbidden as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc
    except DocumentDeleteConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return Response(status_code=204)
