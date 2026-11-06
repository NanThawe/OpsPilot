from __future__ import annotations

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from ollama import Client, ResponseError
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.classification import get_current_user, get_db
from app.core.config import settings
from app.core.permissions import document_access_filter
from app.db.models import (
    Document,
    DocumentChunk,
    DocumentClassification,
    DocumentPage,
    PurchaseOrderExtractionRevision,
    PurchaseOrderReview,
    User,
)
from app.services.auto_indexing import (
    EMBEDDING_MODEL,
    AutoIndexError,
    embed_texts,
    index_document_chunks,
)
from app.services.knowledge_search import (
    escape_like,
    make_search_snippet,
)
from app.services.rag import (
    SYSTEM_PROMPT,
    build_rag_context,
    validate_source_ids,
)

router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge Search"],
)

SEMANTIC_LIMIT_MAX = 20
RAG_RETRIEVAL_LIMIT = 5


class SearchHit(BaseModel):
    document_id: UUID
    document_title: str
    page_number: int
    snippet: str
    source_ref: str


class IndexResponse(BaseModel):
    document_id: UUID
    chunks_indexed: int
    embedding_model: str


class SemanticSearchHit(BaseModel):
    document_id: UUID
    document_title: str
    page_number: int
    snippet: str
    source_ref: str
    similarity: float


class AskRequest(BaseModel):
    question: str = Field(
        min_length=2,
        max_length=500,
    )


class RagDraft(BaseModel):
    supported: bool
    answer: str
    source_ids: list[int] = Field(
        default_factory=list
    )


class RagCitation(BaseModel):
    document_id: UUID
    document_title: str
    page_number: int
    source_ref: str


class AskResponse(BaseModel):
    question: str
    answer: str
    supported: bool
    citations: list[RagCitation]
    model_name: str


def _role_name(user: User) -> str:
    role = getattr(user.role, "value", user.role)
    return str(role).lower()


def approved_knowledge_scope(user: User):
    latest_po_revision = (
        select(
            func.coalesce(
                func.max(
                    PurchaseOrderExtractionRevision.revision_number
                ),
                1,
            )
        )
        .where(
            PurchaseOrderExtractionRevision.document_id
            == Document.id
        )
        .correlate(Document)
        .scalar_subquery()
    )

    approved_po = (
        select(PurchaseOrderReview.document_id)
        .where(
            PurchaseOrderReview.document_id
            == Document.id,
            PurchaseOrderReview.revision_number
            == latest_po_revision,
            PurchaseOrderReview.decision
            == "approved",
        )
        .correlate(Document)
        .exists()
    )

    return and_(
        Document.status == "ready",
        Document.extraction_status == "completed",
        DocumentClassification.review_status
        == "approved",
        document_access_filter(user),
        or_(
            DocumentClassification.predicted_type
            != "purchase_order",
            approved_po,
        ),
    )


@router.get(
    "/search",
    response_model=list[SearchHit],
)
def search_documents(
    q: Annotated[
        str,
        Query(min_length=2, max_length=100),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
    user: Annotated[
        User,
        Depends(get_current_user),
    ],
    limit: Annotated[
        int,
        Query(ge=1, le=50),
    ] = 20,
):
    query = q.strip()

    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                "Search query must contain at least "
                "two characters"
            ),
        )

    pattern = f"%{escape_like(query)}%"

    statement = (
        select(
            DocumentPage,
            Document.title,
        )
        .join(
            Document,
            DocumentPage.document_id
            == Document.id,
        )
        .join(
            DocumentClassification,
            DocumentClassification.document_id
            == Document.id,
        )
        .where(
            approved_knowledge_scope(user),
            or_(
                DocumentPage.text.ilike(
                    pattern,
                    escape="\\",
                ),
                Document.title.ilike(
                    pattern,
                    escape="\\",
                ),
            ),
        )
        .order_by(
            Document.created_at.desc(),
            DocumentPage.page_number,
        )
        .limit(limit)
    )

    rows = db.execute(statement).all()

    return [
        SearchHit(
            document_id=page.document_id,
            document_title=title,
            page_number=page.page_number,
            snippet=make_search_snippet(
                page.text,
                query,
            ),
            source_ref=(
                f"document:{page.document_id}:"
                f"page:{page.page_number}"
            ),
        )
        for page, title in rows
    ]


@router.post(
    "/index/{document_id}",
    response_model=IndexResponse,
)
def index_document(
    document_id: UUID,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
    user: Annotated[
        User,
        Depends(get_current_user),
    ],
):
    """Manual maintenance/re-index endpoint.

    Automatic indexing occurs after approval. This endpoint remains
    admin-only for retries and maintenance.
    """

    if _role_name(user) != "admin":
        raise HTTPException(
            status_code=403,
            detail=(
                "Admin role required for document "
                "indexing"
            ),
        )

    try:
        count = index_document_chunks(
            db,
            document_id,
        )
    except AutoIndexError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return IndexResponse(
        document_id=document_id,
        chunks_indexed=count,
        embedding_model=EMBEDDING_MODEL,
    )


def _semantic_rows(
    *,
    query: str,
    db: Session,
    user: User,
    limit: int,
):
    query_embedding = embed_texts([query])[0]

    distance = (
        DocumentChunk.embedding.cosine_distance(
            query_embedding
        )
        .label("distance")
    )

    statement = (
        select(
            DocumentChunk,
            Document.title,
            distance,
        )
        .join(
            Document,
            DocumentChunk.document_id
            == Document.id,
        )
        .join(
            DocumentClassification,
            DocumentClassification.document_id
            == Document.id,
        )
        .where(
            # Authorization happens in SQL before any
            # retrieved text reaches the LLM.
            approved_knowledge_scope(user),
            DocumentChunk.embedding_model
            == EMBEDDING_MODEL,
        )
        .order_by(distance.asc())
        .limit(limit)
    )

    return db.execute(statement).all()


@router.get(
    "/semantic-search",
    response_model=list[SemanticSearchHit],
)
def semantic_search(
    q: Annotated[
        str,
        Query(min_length=2, max_length=500),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
    user: Annotated[
        User,
        Depends(get_current_user),
    ],
    limit: Annotated[
        int,
        Query(ge=1, le=SEMANTIC_LIMIT_MAX),
    ] = 5,
):
    query = q.strip()

    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                "Search query must contain at least "
                "two characters"
            ),
        )

    rows = _semantic_rows(
        query=query,
        db=db,
        user=user,
        limit=limit,
    )

    hits: list[SemanticSearchHit] = []

    for chunk, title, distance in rows:
        similarity = max(
            -1.0,
            min(
                1.0,
                1.0 - float(distance),
            ),
        )

        hits.append(
            SemanticSearchHit(
                document_id=chunk.document_id,
                document_title=title,
                page_number=chunk.page_number,
                snippet=chunk.content[:500],
                source_ref=(
                    f"document:{chunk.document_id}:"
                    f"page:{chunk.page_number}"
                ),
                similarity=similarity,
            )
        )

    return hits


@router.post(
    "/ask",
    response_model=AskResponse,
)
def ask_documents(
    payload: AskRequest,
    db: Annotated[
        Session,
        Depends(get_db),
    ],
    user: Annotated[
        User,
        Depends(get_current_user),
    ],
):
    question = payload.question.strip()

    if len(question) < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                "Question must contain at least "
                "two characters"
            ),
        )

    rows = _semantic_rows(
        query=question,
        db=db,
        user=user,
        limit=RAG_RETRIEVAL_LIMIT,
    )

    if not rows:
        return AskResponse(
            question=question,
            answer=(
                "I could not find sufficient approved "
                "document evidence accessible to your "
                "account."
            ),
            supported=False,
            citations=[],
            model_name=settings.ollama_model,
        )

    sources = [
        (
            title,
            chunk.page_number,
            chunk.content,
        )
        for chunk, title, _distance in rows
    ]

    context = build_rag_context(sources)

    client = Client(
        host=settings.ollama_base_url,
        timeout=180.0,
    )

    try:
        response = client.chat(
            model=settings.ollama_model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"QUESTION:\n{question}\n\n"
                        f"DOCUMENT EVIDENCE:\n"
                        f"{context}"
                    ),
                },
            ],
            format=RagDraft.model_json_schema(),
            options={"temperature": 0},
        )

        draft = RagDraft.model_validate_json(
            response.message.content or ""
        )

    except (
        ResponseError,
        httpx.HTTPError,
        ValidationError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail="Local RAG generation failed",
        ) from exc

    if not draft.supported:
        return AskResponse(
            question=question,
            answer=draft.answer,
            supported=False,
            citations=[],
            model_name=settings.ollama_model,
        )

    try:
        source_ids = validate_source_ids(
            draft.source_ids,
            len(rows),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "RAG returned invalid source "
                "citations"
            ),
        ) from exc

    citations: list[RagCitation] = []

    for source_id in source_ids:
        chunk, title, _distance = (
            rows[source_id - 1]
        )

        citations.append(
            RagCitation(
                document_id=chunk.document_id,
                document_title=title,
                page_number=chunk.page_number,
                source_ref=(
                    f"document:{chunk.document_id}:"
                    f"page:{chunk.page_number}"
                ),
            )
        )

    return AskResponse(
        question=question,
        answer=draft.answer,
        supported=True,
        citations=citations,
        model_name=settings.ollama_model,
    )
