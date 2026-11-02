from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import (
    enforce_department_access,
    require_roles,
)
from app.db.models import Department, User
from app.db.session import get_db

router = APIRouter(tags=["Access Control"])


class DepartmentResponse(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class AdminOverviewResponse(BaseModel):
    user_count: int
    department_count: int


@router.get(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
)
def get_department(
    department_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    enforce_department_access(current_user, department_id)

    department = db.get(Department, department_id)

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    return department


@router.get(
    "/admin/overview",
    response_model=AdminOverviewResponse,
    dependencies=[Depends(require_roles("admin"))],
)
def admin_overview(
    db: Annotated[Session, Depends(get_db)],
):
    user_count = db.scalar(select(func.count()).select_from(User)) or 0

    department_count = db.scalar(select(func.count()).select_from(Department)) or 0

    return AdminOverviewResponse(
        user_count=user_count,
        department_count=department_count,
    )
