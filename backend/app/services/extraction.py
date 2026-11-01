from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PAGES = 100
MAX_PAGE_CHARS = 50_000
MAX_TOTAL_CHARS = 500_000


class ExtractionError(Exception):
    pass


@dataclass(frozen=True)
class ExtractionResult:
    page_count: int
    pages: list[tuple[int, str]]


def extract_pdf_pages(path: Path) -> ExtractionResult:
    """
    Extract text while preserving original page numbers.

    Blank pages are excluded from the text records.
    """

    try:
        reader = PdfReader(path, strict=True)

        if reader.is_encrypted:
            raise ExtractionError(
                "Password-protected PDFs are not supported"
            )

        page_count = len(reader.pages)

        if page_count > MAX_PAGES:
            raise ExtractionError(
                f"PDF exceeds the {MAX_PAGES}-page limit"
            )

        extracted_pages = []
        total_chars = 0

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            text = page.extract_text() or ""

            # Normalise basic text formatting.
            text = text.replace("\x00", "").strip()

            if len(text) > MAX_PAGE_CHARS:
                raise ExtractionError(
                    f"Page {page_number} exceeds the text limit"
                )

            total_chars += len(text)

            if total_chars > MAX_TOTAL_CHARS:
                raise ExtractionError(
                    "PDF exceeds the total extracted text limit"
                )

            if text:
                extracted_pages.append(
                    (page_number, text)
                )

        return ExtractionResult(
            page_count=page_count,
            pages=extracted_pages,
        )

    except (PdfReadError, ValueError) as exc:
        raise ExtractionError(
            "Unable to extract text from this PDF"
        ) from exc