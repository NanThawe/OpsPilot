from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from ollama import Client, ResponseError
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
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
from app.services.knowledge_search import (
    escape_like,
    make_search_snippet,
)
from app.services.rag import (
    SYSTEM_PROMPT,
    build_rag_context,
    validate_source_ids,
)
from app.services.semantic_search import (
    EMBEDDING_MODEL,
    EmbeddingServiceError,
    chunk_text,
    embed_texts,
)

router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge Search"],
)


class IndexResponse(BaseModel):
    document_id: UUID
    chunks_indexed: int
    embedding_model: str


class SearchHit(BaseModel):
    document_id: UUID
    document_title: str
    page_number: int
    snippet: str
    source_ref: str


class SemanticSearchHit(BaseModel):
    document_id: UUID
    document_title: str
    page_number: int
    snippet: str
    source_ref: str
    similarity: float


def approved_knowledge_scope(user: User):
    latest_po_revision = (
        select(
            func.coalesce(
                func.max(PurchaseOrderExtractionRevision.revision_number),
                1,
            )
        )
        .where(PurchaseOrderExtractionRevision.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )

    approved_po = (
        select(PurchaseOrderReview.document_id)
        .where(
            PurchaseOrderReview.document_id == Document.id,
            PurchaseOrderReview.revision_number == latest_po_revision,
            PurchaseOrderReview.decision == "approved",
        )
        .correlate(Document)
        .exists()
    )

    return and_(
        Document.status == "ready",
        Document.extraction_status == "completed",
        DocumentClassification.review_status == "approved",
        document_access_filter(user),
        or_(
            DocumentClassification.predicted_type != "purchase_order",
            approved_po,
        ),
    )


@router.get("/search", response_model=list[SearchHit])
def search_documents(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    query = q.strip()

    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail="Search query must contain at least two characters",
        )

    pattern = f"%{escape_like(query)}%"

    statement = (
        select(DocumentPage, Document.title)
        .join(
            Document,
            DocumentPage.document_id == Document.id,
        )
        .join(
            DocumentClassification,
            DocumentClassification.document_id == Document.id,
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
            source_ref=(f"document:{page.document_id}:page:{page.page_number}"),
        )
        for page, title in rows
    ]


@router.post(
    "/index/{document_id}",
    response_model=IndexResponse,
)
def index_document(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    document = db.scalar(
        select(Document)
        .join(
            DocumentClassification,
            DocumentClassification.document_id == Document.id,
        )
        .where(
            Document.id == document_id,
            approved_knowledge_scope(user),
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Approved document not found",
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()

    records = []

    for page in pages:
        chunks = chunk_text(page.text)

        for index, content in enumerate(chunks):
            records.append((page.page_number, index, content))

    if not records:
        raise HTTPException(
            status_code=422,
            detail="Document contains no indexable text",
        )

    if len(records) > 200:
        raise HTTPException(
            status_code=413,
            detail="Document exceeds the MVP indexing limit",
        )

    try:
        vectors = []

        for start in range(0, len(records), 16):
            batch = [content for _, _, content in records[start : start + 16]]

            vectors.extend(embed_texts(batch))

    except EmbeddingServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    try:
        # Replace existing chunks only after embedding succeeds.
        db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )

        for (page_number, chunk_index, content), vector in zip(
            records,
            vectors,
            strict=True,
        ):
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    content=content,
                    embedding=vector,
                    embedding_model=EMBEDDING_MODEL,
                )
            )

        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Failed to save document embeddings",
        ) from exc

    return IndexResponse(
        document_id=document_id,
        chunks_indexed=len(records),
        embedding_model=EMBEDDING_MODEL,
    )


@router.get(
    "/semantic-search",
    response_model=list[SemanticSearchHit],
)
def semantic_search(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
):
    query = q.strip()

    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail="Search query is too short",
        )

    try:
        query_vector = embed_texts([query])[0]

    except EmbeddingServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")

    statement = (
        select(
            DocumentChunk,
            Document.title,
            distance,
        )
        .join(
            Document,
            DocumentChunk.document_id == Document.id,
        )
        .join(
            DocumentClassification,
            DocumentClassification.document_id == Document.id,
        )
        .where(
            approved_knowledge_scope(user),
            DocumentChunk.embedding_model == EMBEDDING_MODEL,
        )
        .order_by(distance)
        .limit(limit)
    )

    rows = db.execute(statement).all()

    return [
        SemanticSearchHit(
            document_id=chunk.document_id,
            document_title=title,
            page_number=chunk.page_number,
            snippet=chunk.content,
            source_ref=(f"document:{chunk.document_id}:page:{chunk.page_number}"),
            similarity=round(1.0 - float(dist), 4),
        )
        for chunk, title, dist in rows
    ]

class AskRequest(BaseModel):
    question: str = Field(
        min_length=2,
        max_length=500,
    )


class RagDraft(BaseModel):
    supported: bool
    answer: str
    source_ids: list[int]


class AskResponse(BaseModel):
    question: str
    answer: str
    supported: bool
    citations: list[SemanticSearchHit]
    model_name: str

@router.post(
    "/ask",
    response_model=AskResponse,
)
def ask_documents(
    payload: AskRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    question = payload.question.strip()

    if len(question) < 2:
        raise HTTPException(
            status_code=422,
            detail="Question is too short",
        )

    # Reuse the existing permission-aware semantic search.
    sources = semantic_search(
        q=question,
        db=db,
        user=user,
        limit=5,
    )

    model_name = f"ollama:{settings.ollama_model}"

    if not sources:
        return AskResponse(
            question=question,
            answer=(
                "I could not find sufficient information "
                "in the approved documents."
            ),
            supported=False,
            citations=[],
            model_name=model_name,
        )

    context = build_rag_context(
        [
            (
                source.document_title,
                source.page_number,
                source.snippet,
            )
            for source in sources
        ]
    )

    user_prompt = (
        f"QUESTION:\n{question}\n\n"
        f"DOCUMENT EVIDENCE:\n{context}\n\n"
        "Answer using only the document evidence. "
        "If it does not directly support the answer, "
        "set supported to false. "
        "Return JSON matching the required schema."
    )

    try:
        client = Client(
            host=settings.ollama_base_url,
            timeout=180.0,
        )

        response = client.chat(
            model=settings.ollama_model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_prompt,
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
            detail="RAG answer generation failed",
        ) from exc

    if not draft.supported:
        return AskResponse(
            question=question,
            answer=(
                "I could not confirm an answer "
                "from the available document evidence."
            ),
            supported=False,
            citations=[],
            model_name=model_name,
        )

    if not draft.answer.strip():
        raise HTTPException(
            status_code=503,
            detail="AI returned an empty answer",
        )

    try:
        valid_ids = validate_source_ids(
            draft.source_ids,
            len(sources),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="AI returned invalid citations",
        ) from exc

    # Resolve citations against trusted database results.
    # Never trust the LLM to invent source references.
    citations = []
    seen_pages = set()

    for source_id in valid_ids:
        source = sources[source_id - 1]

        page_key = (
            source.document_id,
            source.page_number,
        )

        if page_key in seen_pages:
            continue

        seen_pages.add(page_key)
        citations.append(source)

    return AskResponse(
        question=question,
        answer=draft.answer.strip(),
        supported=True,
        citations=citations,
        model_name=model_name,
    )