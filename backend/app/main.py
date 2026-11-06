import logging
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.access import router as access_router
from app.api.agent import router as agent_router
from app.api.agent_workflows import router as workflow_router
from app.api.auth import router as auth_router
from app.api.classification import router as classification_router
from app.api.document_delete import router as document_delete_router
from app.api.documents import router as documents_router
from app.api.extraction import router as extraction_router
from app.api.knowledge import router as knowledge_router
from app.core.observability import (
    configure_logging,
    log_event,
    make_request_id,
    request_id_context,
)
from app.db.session import get_engine

configure_logging()

logger = logging.getLogger("opspilot.api")

app = FastAPI(
    title="OpsPilot API",
    description="AI-powered procurement and operations copilot",
    version="0.1.0",
)
app.include_router(auth_router)
app.include_router(access_router)
app.include_router(documents_router)
app.include_router(extraction_router)
app.include_router(classification_router)
app.include_router(knowledge_router)
app.include_router(agent_router)
app.include_router(workflow_router)
app.include_router(document_delete_router)



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

@app.middleware("http")
async def request_observability(
    request: Request,
    call_next,
):
    request_id = make_request_id(
        request.headers.get("X-Request-ID")
    )

    context_token = request_id_context.set(request_id)
    started = perf_counter()

    try:
        response = await call_next(request)

        duration_ms = round(
            (perf_counter() - started) * 1000,
            2,
        )

        route = request.scope.get("route")
        route_path = getattr(
            route,
            "path",
            request.url.path,
        )

        log_event(
            logger,
            "http_request",
            method=request.method,
            route=route_path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        response.headers["X-Request-ID"] = request_id

        return response

    except Exception as exc:
        duration_ms = round(
            (perf_counter() - started) * 1000,
            2,
        )

        logger.exception(
            "Unhandled request exception",
            extra={
                "event": "http_request_error",
                "event_data": {
                    "method": request.method,
                    "route": request.url.path,
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                },
            },
        )

        raise

    finally:
        request_id_context.reset(context_token)

