"""Reset OpsPilot demo/transactional data while preserving users and departments.

Dry-run by default. Pass --yes to perform destructive changes.

Examples
--------
Local:
    python backend/scripts/reset_demo_data.py
    python backend/scripts/reset_demo_data.py --yes

From backend/:
    python scripts/reset_demo_data.py --yes

Docker:
    docker compose exec backend python backend/scripts/reset_demo_data.py --yes
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(PROJECT_ROOT / ".env")

from app.db.session import get_engine  # noqa: E402

# Only these application tables are eligible for truncation.
# Missing tables are ignored so the script stays compatible across migrations.
RESET_TABLES = {
    "agent_audit_events",
    "agent_workflows",
    "document_chunks",
    "document_classifications",
    "document_pages",
    "documents",
    "procurement_follow_ups",
    "purchase_order_extraction_revisions",
    "purchase_order_extractions",
    "purchase_order_lines",
    "purchase_order_reviews",
}

# LangGraph checkpoint data can be cleared safely while retaining
# checkpoint_migrations, which records the checkpoint schema version.
CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
}

PRESERVED_TABLES = {
    "users",
    "departments",
    "alembic_version",
    "checkpoint_migrations",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clear OpsPilot demo documents, approvals, agent workflows, "
            "vector chunks and checkpoint state while preserving users/departments."
        )
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually perform the reset. Without this flag the script is dry-run only.",
    )
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Keep files in DOCUMENT_STORAGE_DIR instead of deleting them.",
    )
    return parser.parse_args()


def storage_dir() -> Path:
    configured = os.getenv("DOCUMENT_STORAGE_DIR", "data/private_documents")
    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def clear_storage(path: Path) -> int:
    if not path.exists():
        return 0

    removed = 0
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1

    return removed


def main() -> None:
    args = parse_args()

    environment = (
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or "development"
    ).lower()

    if environment in {"prod", "production"}:
        raise SystemExit(
            "Refusing to reset while APP_ENV/ENVIRONMENT indicates production."
        )

    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    targets = sorted(
        (RESET_TABLES | CHECKPOINT_TABLES) & existing_tables
    )

    unknown = sorted(
        existing_tables
        - RESET_TABLES
        - CHECKPOINT_TABLES
        - PRESERVED_TABLES
    )

    print("OpsPilot demo reset")
    print("-------------------")
    print(
        "Database:",
        engine.url.render_as_string(hide_password=True),
    )
    print("Mode:", "EXECUTE" if args.yes else "DRY RUN")
    print()
    print("Tables to clear:")
    for table in targets:
        print(f"  - {table}")

    print()
    print("Explicitly preserved:")
    for table in sorted(PRESERVED_TABLES & existing_tables):
        print(f"  - {table}")

    if unknown:
        print()
        print("Other tables left untouched:")
        for table in unknown:
            print(f"  - {table}")

    store = storage_dir()
    print()
    print("Document storage:", store)
    print(
        "Storage action:",
        "keep" if args.keep_files else "clear contents",
    )

    if not args.yes:
        print()
        print(
            "Dry run only. Re-run with --yes after reviewing the target list."
        )
        return

    if targets:
        quoted = ", ".join(f'"{name}"' for name in targets)
        statement = (
            f"TRUNCATE TABLE {quoted} "
            "RESTART IDENTITY CASCADE"
        )
        with engine.begin() as connection:
            connection.execute(text(statement))

    removed_files = 0
    if not args.keep_files:
        removed_files = clear_storage(store)
        store.mkdir(parents=True, exist_ok=True)

    print()
    print("Reset complete.")
    print(f"Cleared {len(targets)} database tables.")
    if args.keep_files:
        print("Document files preserved.")
    else:
        print(f"Removed {removed_files} storage entries.")
    print("Demo users and departments were preserved.")


if __name__ == "__main__":
    main()
