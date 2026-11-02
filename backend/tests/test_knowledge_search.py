from app.services.knowledge_search import (
    escape_like,
    make_search_snippet,
)


def test_search_escapes_sql_wildcards():
    assert escape_like("50%_complete") == "50\\%\\_complete"


def test_search_escapes_backslashes():
    assert escape_like("a\\b") == "a\\\\b"


def test_snippet_finds_case_insensitive_match():
    text = (
        "Purchase order for protective equipment. Twenty SAFETY HELMETS were ordered."
    )

    snippet = make_search_snippet(text, "safety helmets")

    assert "SAFETY HELMETS" in snippet


def test_snippet_limits_returned_text():
    text = "A" * 1000 + "purchase order" + "B" * 1000

    snippet = make_search_snippet(text, "purchase order")

    assert "purchase order" in snippet
    assert len(snippet) < 260


def test_snippet_handles_missing_match():
    snippet = make_search_snippet(
        "An invoice for delivery services.",
        "purchase order",
    )

    assert snippet == "An invoice for delivery services."
