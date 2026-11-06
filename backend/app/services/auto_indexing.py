from __future__ import annotations

import logging
from uuid import UUID

import httpx
from ollama import Client, ResponseError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Document,
    DocumentChunk,
    DocumentClassification,
    DocumentPage,
    PurchaseOrderExtractionRevision,
    PurchaseOrderReview,
)
from app.db.session import get_engine

logger = logging.getLogger("opspilot.auto_index")

EMBEDDING_MODEL = "nomic-embed-text"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


class AutoIndexError(Exception):
    """Raised when a document cannot safely be indexed."""


def chunk_text(text: str) -> list[str]:
    normalized = " ".join(text.split())

    if not normalized:
        return []

    if len(normalized) <= CHUNK_SIZE:
        return [normalized]

    chunks: list[str] = []
    start = 0

    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        chunk = normalized[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(normalized):
            break

        start = max(end - CHUNK_OVERLAP, start + 1)

    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = Client(
        host=settings.ollama_base_url,
        timeout=180.0,
    )

    try:
        response = client.embed(
            model=EMBEDDING_MODEL,
            input=texts,
        )
    except (ResponseError, httpx.HTTPError) as exc:
        raise AutoIndexError(
            "Local embedding service is unavailable"
        ) from exc

    embeddings = response.embeddings

    if len(embeddings) != len(texts):
        raise AutoIndexError(
            "Embedding service returned an unexpected result count"
        )

    return [list(vector) for vector in embeddings]


def trusted_for_knowledge(
    db: Session,
    document_id: UUID,
) -> bool:
    """Return True only when the document may enter the trusted AI index."""

    row = db.execute(
        select(
            Document.status,
            Document.extraction_status,
            DocumentClassification.review_status,
            DocumentClassification.predicted_type,
        )
        .join(
            DocumentClassification,
            DocumentClassification.document_id == Document.id,
        )
        .where(Document.id == document_id)
    ).one_or_none()

    if row is None:
        return False

    (
        status,
        extraction_status,
        review_status,
        predicted_type,
    ) = row

    if (
        status != "ready"
        or extraction_status != "completed"
        or review_status != "approved"
    ):
        return False

    # Non-PO documents become trusted after classification approval.
    if predicted_type != "purchase_order":
        return True

    # Purchase orders become trusted only after their latest structured
    # extraction revision receives business approval.
    latest_revision = db.scalar(
        select(
            func.max(
                PurchaseOrderExtractionRevision.revision_number
            )
        ).where(
            PurchaseOrderExtractionRevision.document_id
            == document_id
        )
    )

    if latest_revision is None:
        return False

    decision = db.scalar(
        select(PurchaseOrderReview.decision).where(
            PurchaseOrderReview.document_id == document_id,
            PurchaseOrderReview.revision_number
            == latest_revision,
        )
    )

    return decision == "approved"


def index_document_chunks(
    db: Session,
    document_id: UUID,
) -> int:
    """Rebuild vector chunks for one trusted document.

    This function is idempotent. Existing chunks for the document are
    replaced only after the document passes the trusted-knowledge check.
    """

    if not trusted_for_knowledge(db, document_id):
        raise AutoIndexError(
            "Document is not approved for the trusted knowledge index"
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()

    chunk_records: list[tuple[int, int, str]] = []
    chunk_index = 0

    for page in pages:
        for content in chunk_text(page.text):
            chunk_records.append(
                (
                    chunk_index,
                    page.page_number,
                    content,
                )
            )
            chunk_index += 1

    if not chunk_records:
        raise AutoIndexError(
            "Document contains no indexable extracted text"
        )

    embeddings = embed_texts(
        [content for _, _, content in chunk_records]
    )

    db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
    )

    for (
        (index, page_number, content),
        embedding,
    ) in zip(
        chunk_records,
        embeddings,
        strict=True,
    ):
        db.add(
            DocumentChunk(
                document_id=document_id,
                page_number=page_number,
                chunk_index=index,
                content=content,
                embedding=embedding,
                embedding_model=EMBEDDING_MODEL,
            )
        )

    db.commit()

    return len(chunk_records)


def auto_index_document(document_id: UUID) -> None:
    """FastAPI BackgroundTasks entry point.

    Approval has already been committed before this runs. Any indexing
    failure is logged and does not reverse the business approval.
    """

    engine = get_engine()

    with Session(engine) as db:
        try:
            count = index_document_chunks(
                db,
                document_id,
            )
            logger.info(
                "auto_index_success document_id=%s chunks=%s",
                document_id,
                count,
            )
        except Exception:
            db.rollback()
            logger.exception(
                "auto_index_failed document_id=%s",
                document_id,
            )
