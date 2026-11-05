from fastapi.testclient import TestClient

from app.main import app


def test_database_health_when_unavailable(monkeypatch):
    def unavailable_engine():
        raise RuntimeError("Database is offline")

    monkeypatch.setattr(
        "app.main.get_engine",
        unavailable_engine,
    )

    client = TestClient(app)
    response = client.get("/db-health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
