import pytest

from app.services.semantic_search import chunk_text


def test_empty_document_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n   ") == []


def test_short_document_produces_one_chunk():
    text = "Purchase order for barcode scanners."

    assert chunk_text(text) == [text]


def test_long_document_produces_multiple_chunks():
    text = "Portable barcode scanner. " * 100

    chunks = chunk_text(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 900 for chunk in chunks)


def test_invalid_chunk_parameters():
    with pytest.raises(ValueError):
        chunk_text("test", chunk_size=100, overlap=100)
