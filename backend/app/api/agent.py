from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.procurement import (
    ProcurementAgentError,
    run_procurement_agent,
)
from app.api.classification import (
    get_current_user,
    get_db,
)
from app.db.models import User

router = APIRouter(
    prefix="/agent",
    tags=["Procurement Agent"],
)


class AgentRequest(BaseModel):
    message: str = Field(
        min_length=3,
        max_length=500,
    )


class AgentResponse(BaseModel):
    action: str
    tool_used: str
    answer: str
    citations: list[dict[str, Any]]


@router.post(
    "/run",
    response_model=AgentResponse,
)
def run_agent(
    payload: AgentRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        result = run_procurement_agent(
            question=payload.message,
            db=db,
            user=user,
        )

    except ProcurementAgentError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    return AgentResponse(
        action=result.get("action", "unknown"),
        tool_used=result.get("tool_used", "none"),
        answer=result.get("answer", ""),
        citations=result.get("citations", []),
    )