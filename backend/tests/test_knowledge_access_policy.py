from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.api import knowledge


def fake_user(role: str):
    return SimpleNamespace(role=role)


def test_indexing_rejects_staff_before_db_access():
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        knowledge.index_document(
            document_id=UUID(
                "00000000-0000-0000-0000-000000000001"
            ),
            db=db,
            user=fake_user("staff"),
        )

    assert exc.value.status_code == 403
    db.scalar.assert_not_called()


def test_indexing_rejects_manager_before_db_access():
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        knowledge.index_document(
            document_id=UUID(
                "00000000-0000-0000-0000-000000000001"
            ),
            db=db,
            user=fake_user("manager"),
        )

    assert exc.value.status_code == 403
    db.scalar.assert_not_called()


def test_role_name_normalizes_roles():
    assert knowledge._role_name(fake_user("admin")) == "admin"
    assert knowledge._role_name(fake_user("staff")) == "staff"
    assert knowledge._role_name(fake_user("manager")) == "manager"


def test_read_endpoints_do_not_have_admin_role_gate():
    semantic_names = set(
        knowledge.semantic_search.__code__.co_names
    )
    rag_names = set(
        knowledge.ask_documents.__code__.co_names
    )

    assert "_role_name" not in semantic_names
    assert "_role_name" not in rag_names
