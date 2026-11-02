import re


def escape_like(value: str) -> str:
    """Escape SQL LIKE wildcard characters."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def make_search_snippet(
    text: str,
    query: str,
    before: int = 80,
    after: int = 140,
) -> str:
    """Return a short source-text excerpt around a match."""

    match = re.search(
        re.escape(query),
        text,
        flags=re.IGNORECASE,
    )

    if match is None:
        return re.sub(r"\s+", " ", text[:220]).strip()

    start = max(0, match.start() - before)
    end = min(len(text), match.end() + after)

    excerpt = re.sub(
        r"\s+",
        " ",
        text[start:end],
    ).strip()

    if start > 0:
        excerpt = "..." + excerpt

    if end < len(text):
        excerpt += "..."

    return excerpt
