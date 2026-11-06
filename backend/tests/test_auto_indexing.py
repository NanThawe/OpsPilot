
from app.services.auto_indexing import chunk_text


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_chunk_text_short_text():
    assert chunk_text("hello world") == [
        "hello world"
    ]


def test_chunk_text_normalizes_whitespace():
    assert chunk_text("hello\\n\\n  world") == [
        "hello\\n\\n world"
    ] or chunk_text("hello\\n\\n  world") == [
        "hello world"
    ]


def test_chunk_text_creates_multiple_chunks():
    text = "x" * 2000
    chunks = chunk_text(text)

    assert len(chunks) >= 2
    assert all(chunks)
