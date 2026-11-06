from types import SimpleNamespace
from uuid import UUID

from app.services.document_delete import (
    DocumentDeleteForbidden,
    role_name,
)


def fake_user(
    role: str,
    user_id: str = "00000000-0000-0000-0000-000000000001",
):
    return SimpleNamespace(
        role=role,
        id=UUID(user_id),
    )


def test_role_name_normalizes_string_role():
    assert role_name(fake_user("admin")) == "admin"
    assert role_name(fake_user("staff")) == "staff"


def test_delete_forbidden_error_message():
    exc = DocumentDeleteForbidden("not allowed")
    assert str(exc) == "not allowed"
