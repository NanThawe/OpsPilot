import re

import httpx
from ollama import Client, ResponseError

from app.core.config import settings

EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIMENSIONS = 768


class EmbeddingServiceError(Exception):
    pass


def chunk_text(
    text: str,
    chunk_size: int = 900,
    overlap: int = 140,
) -> list[str]:
    if chunk_size <= overlap or overlap < 0:
        raise ValueError("Invalid chunking parameters")

    clean = re.sub(r"\s+", " ", text).strip()

    if not clean:
        return []

    chunks = []
    start = 0

    while start < len(clean):
        end = min(start + chunk_size, len(clean))

        if end < len(clean):
            boundary = clean.rfind(
                " ",
                start + chunk_size // 2,
                end,
            )

            if boundary > start:
                end = boundary

        chunk = clean[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(clean):
            break

        start = max(end - overlap, start + 1)

    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    try:
        client = Client(
            host=settings.ollama_base_url,
            timeout=180.0,
        )

        response = client.embed(
            model=EMBEDDING_MODEL,
            input=texts,
        )

    except (ResponseError, httpx.HTTPError) as exc:
        raise EmbeddingServiceError("Local embedding request failed") from exc

    embeddings = response.embeddings

    if len(embeddings) != len(texts):
        raise EmbeddingServiceError("Unexpected number of embeddings")

    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in embeddings):
        raise EmbeddingServiceError("Invalid embedding dimensions")

    return [[float(value) for value in vector] for vector in embeddings]
