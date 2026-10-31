from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.access import router as access_router
from app.api.auth import router as auth_router
from app.db.session import get_engine

app = FastAPI(
    title="OpsPilot API",
    description="AI-powered procurement and operations copilot",
    version="0.1.0",
)
app.include_router(auth_router)
app.include_router(access_router)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Check whether the API is running."""
    return {
        "status": "ok",
        "service": "opspilot-api",
    }

@app.get("/db-health", tags=["System"])
def database_health_check() -> dict[str, str]:
    """Verify connectivity to PostgreSQL."""

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))

    except (RuntimeError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
    }