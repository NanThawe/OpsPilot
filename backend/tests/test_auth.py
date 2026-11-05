from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_user_id,
    hash_password,
    verify_password,
)
from app.main import app


def test_password_hashing():
    password = "SecureTestPassword123!"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("incorrect-password", hashed)


def test_jwt_round_trip(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        SecretStr("unit-test-" + "a" * 64),
    )

    user_id = uuid4()

    token = create_access_token(user_id)

    assert decode_user_id(token) == user_id


def test_profile_requires_authentication():
    client = TestClient(app)

    response = client.get("/auth/me")

    assert response.status_code == 401
