from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import settings


@lru_cache
def get_engine() -> Engine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )