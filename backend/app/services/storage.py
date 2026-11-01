import hashlib
import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import settings

MAX_FILE_SIZE = 10 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class InvalidPdfError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


def get_storage_path(storage_key: str) -> Path:
    """Resolve a generated storage key safely."""

    if not re.fullmatch(r"[0-9a-f]{32}\.pdf", storage_key):
        raise ValueError("Invalid storage key")

    root = settings.document_storage_dir.resolve()
    path = (root / storage_key).resolve()

    if not path.is_relative_to(root):
        raise ValueError("Storage path is outside the permitted directory")

    return path


def save_pdf(upload: UploadFile) -> tuple[str, str, int]:
    """
    Validate and save a PDF.

    Returns:
        storage_key, sha256, size_bytes
    """

    filename = upload.filename or ""

    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or not filename.lower().endswith(".pdf")
    ):
        raise InvalidPdfError("A valid PDF filename is required")

    if upload.content_type != "application/pdf":
        raise InvalidPdfError("Only application/pdf is accepted")

    root = settings.document_storage_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)

    storage_key = f"{uuid4().hex}.pdf"
    final_path = get_storage_path(storage_key)
    temporary_path = root / f".{uuid4().hex}.upload"

    hasher = hashlib.sha256()
    total_size = 0
    first_chunk = True

    try:
        with temporary_path.open("xb") as output:
            while True:
                chunk = upload.file.read(CHUNK_SIZE)

                if not chunk:
                    break

                if first_chunk:
                    if not chunk.startswith(b"%PDF-"):
                        raise InvalidPdfError(
                            "File does not have a PDF signature"
                        )

                    first_chunk = False

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise FileTooLargeError(
                        "Maximum file size is 10 MB"
                    )

                hasher.update(chunk)
                output.write(chunk)

        if total_size == 0:
            raise InvalidPdfError("PDF file is empty")

        # Check whether pypdf can read the file structure.
        try:
            with temporary_path.open("rb") as pdf_file:
                reader = PdfReader(pdf_file, strict=True)

                if reader.is_encrypted:
                    raise InvalidPdfError(
                        "Password-protected PDFs are not supported"
                    )

                if len(reader.pages) == 0:
                    raise InvalidPdfError(
                        "PDF must contain at least one page"
                    )

        except (PdfReadError, ValueError) as exc:
            raise InvalidPdfError(
                "Invalid or unsupported PDF"
            ) from exc

        temporary_path.replace(final_path)

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return storage_key, hasher.hexdigest(), total_size


def verify_file_checksum(
    path: Path,
    expected_sha256: str | None,
) -> bool:
    """Check whether stored file contents match the recorded hash."""

    if expected_sha256 is None:
        return False

    hasher = hashlib.sha256()

    with path.open("rb") as stored_file:
        while True:
            chunk = stored_file.read(CHUNK_SIZE)

            if not chunk:
                break

            hasher.update(chunk)

    return hasher.hexdigest() == expected_sha256