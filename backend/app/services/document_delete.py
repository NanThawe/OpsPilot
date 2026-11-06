from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentClassification, User

logger = logging.getLogger("opspilot.document_delete")


class DocumentDeleteError(Exception):
    pass


class DocumentDeleteForbidden(DocumentDeleteError):
    pass


class DocumentDeleteConflict(DocumentDeleteError):
    pass


def role_name(user: User) -> str:
    role = getattr(user.role, "value", user.role)
    return str(role).lower()


def _table_exists(db: Session, table_name: str) -> bool:
    return table_name in set(inspect(db.get_bind()).get_table_names())


def _exists_for_document(
    db: Session,
    table_name: str,
    document_id: UUID,
) -> bool:
    if not _table_exists(db, table_name):
        return False

    statement = text(
        f'SELECT EXISTS (SELECT 1 FROM "{table_name}" '
        f'WHERE document_id = :document_id)'
    )
    return bool(
        db.scalar(statement, {"document_id": document_id})
    )


def _approved_po_review_exists(
    db: Session,
    document_id: UUID,
) -> bool:
    if not _table_exists(db, "purchase_order_reviews"):
        return False

    return bool(
        db.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM purchase_order_reviews
                    WHERE document_id = :document_id
                      AND decision = 'approved'
                )
                """
            ),
            {"document_id": document_id},
        )
    )


def assert_document_deletable(
    db: Session,
    *,
    document: Document,
    user: User,
) -> None:
    admin = role_name(user) == "admin"

    if not admin and document.created_by_id != user.id:
        raise DocumentDeleteForbidden(
            "Only the document creator or an administrator can delete this document"
        )

    classification = db.get(DocumentClassification, document.id)

    if (
        not admin
        and classification is not None
        and classification.review_status == "approved"
    ):
        raise DocumentDeleteConflict(
            "Approved documents cannot be deleted by staff"
        )

    if _exists_for_document(db, "agent_workflows", document.id):
        raise DocumentDeleteConflict(
            "Document has agent workflow history and cannot be deleted"
        )

    if _exists_for_document(db, "procurement_follow_ups", document.id):
        raise DocumentDeleteConflict(
            "Document has follow-up history and cannot be deleted"
        )

    if _approved_po_review_exists(db, document.id):
        raise DocumentDeleteConflict(
            "Approved purchase orders cannot be deleted"
        )

    if (
        not admin
        and _exists_for_document(
            db,
            "purchase_order_reviews",
            document.id,
        )
    ):
        raise DocumentDeleteConflict(
            "Reviewed purchase orders cannot be deleted by staff"
        )


def _delete_nonfinal_po_reviews(
    db: Session,
    document_id: UUID,
) -> None:
    if not _table_exists(db, "purchase_order_reviews"):
        return

    db.execute(
        text(
            """
            DELETE FROM purchase_order_reviews
            WHERE document_id = :document_id
              AND decision <> 'approved'
            """
        ),
        {"document_id": document_id},
    )


def _storage_root() -> Path:
    configured = os.getenv(
        "DOCUMENT_STORAGE_DIR",
        "data/private_documents",
    )
    return Path(configured).resolve()


def _safe_storage_path(
    storage_key: str | None,
) -> Path | None:
    if not storage_key:
        return None

    root = _storage_root()
    candidate = (root / storage_key).resolve()

    if candidate == root or root not in candidate.parents:
        logger.warning(
            "document_file_delete_skipped unsafe_storage_key=%s",
            storage_key,
        )
        return None

    return candidate


def delete_document_record(
    db: Session,
    *,
    document: Document,
    user: User,
) -> None:
    assert_document_deletable(
        db,
        document=document,
        user=user,
    )

    document_id = document.id
    storage_path = _safe_storage_path(document.storage_key)

    _delete_nonfinal_po_reviews(
        db,
        document_id,
    )

    try:
        db.delete(document)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DocumentDeleteConflict(
            "Document is referenced by protected records and cannot be deleted"
        ) from exc

    if storage_path is not None and storage_path.exists():
        try:
            storage_path.unlink()
        except OSError:
            logger.exception(
                "document_file_delete_failed document_id=%s path=%s",
                document_id,
                storage_path,
            )

    logger.info(
        "document_deleted document_id=%s actor_id=%s",
        document_id,
        user.id,
    )
