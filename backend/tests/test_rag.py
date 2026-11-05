import pytest

from app.services.rag import (
    build_rag_context,
    validate_source_ids,
)


def test_context_contains_numbered_sources():
    context = build_rag_context(
        [
            (
                "Purchase Order 002",
                2,
                "Batch A is due 10 Nov 2026.",
            ),
        ]
    )

    assert "[SOURCE 1]" in context
    assert "Purchase Order 002" in context
    assert "Page: 2" in context
    assert "10 Nov 2026" in context


def test_valid_citations():
    assert validate_source_ids([2, 1, 2], 3) == [2, 1]


def test_missing_citations_rejected():
    with pytest.raises(ValueError):
        validate_source_ids([], 3)


def test_invalid_citations_rejected():
    with pytest.raises(ValueError):
        validate_source_ids([4], 3)