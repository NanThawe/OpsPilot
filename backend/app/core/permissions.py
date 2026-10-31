from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.db.models import User


def require_roles(*allowed_roles: str):
    """Require the authenticated user to have an allowed role."""

    def check_role(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return current_user

    return check_role


def enforce_department_access(
    current_user: User,
    department_id: UUID,
) -> None:
    """Allow access to own department, or any department for admins."""

    if current_user.role == "admin":
        return

    if current_user.department_id != department_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )