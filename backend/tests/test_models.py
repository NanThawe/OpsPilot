from app.db.base import Base
from app.db.models import Department, User
from sqlalchemy import CheckConstraint


def test_models_are_registered():
    tables = Base.metadata.tables

    assert "departments" in tables
    assert "users" in tables


def test_user_department_foreign_key():
    foreign_keys = {
        fk.target_fullname for fk in User.__table__.c.department_id.foreign_keys
    }

    assert "departments.id" in foreign_keys


def test_user_role_constraint():
    constraints = User.__table__.constraints

    assert any(
        isinstance(constraint, CheckConstraint) and constraint.name == "ck_users_role"
        for constraint in constraints
    )


def test_department_has_unique_name():
    assert Department.__table__.c.name.unique is True
