from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.db.base import Base
from app.db.models import Department, User
from app.db.session import get_db
from app.main import app


@pytest.fixture
def context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as db:
        finance = Department(name="Finance")
        operations = Department(name="Operations")
        it = Department(name="IT")

        db.add_all([finance, operations, it])
        db.flush()

        finance_user = User(
            email="finance@test.local",
            role="staff",
            department_id=finance.id,
            password_hash="test-only",
        )

        admin_user = User(
            email="admin@test.local",
            role="admin",
            department_id=it.id,
            password_hash="test-only",
        )

        db.add_all([finance_user, admin_user])
        db.commit()

    def override_db():
        with Session(engine) as db:
            yield db

    def login_as(user):
        app.dependency_overrides[get_current_user] = lambda: user

    app.dependency_overrides[get_db] = override_db

    try:
        yield SimpleNamespace(
            client=TestClient(app),
            login_as=login_as,
            finance=finance,
            operations=operations,
            finance_user=finance_user,
            admin_user=admin_user,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_department_requires_login(context):
    response = context.client.get(f"/departments/{context.finance.id}")

    assert response.status_code == 401


def test_staff_can_access_own_department(context):
    context.login_as(context.finance_user)

    response = context.client.get(f"/departments/{context.finance.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Finance"


def test_staff_cannot_access_other_department(context):
    context.login_as(context.finance_user)

    response = context.client.get(f"/departments/{context.operations.id}")

    assert response.status_code == 403


def test_admin_can_access_other_department(context):
    context.login_as(context.admin_user)

    response = context.client.get(f"/departments/{context.operations.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Operations"


def test_staff_cannot_access_admin_overview(context):
    context.login_as(context.finance_user)

    response = context.client.get("/admin/overview")

    assert response.status_code == 403


def test_admin_can_access_overview(context):
    context.login_as(context.admin_user)

    response = context.client.get("/admin/overview")

    assert response.status_code == 200
    assert response.json() == {
        "user_count": 2,
        "department_count": 3,
    }
