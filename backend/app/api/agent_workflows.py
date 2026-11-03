from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents.approval_workflow import build_approval_graph
from app.agents.followup_drafting import (
    FollowUpDraftError,
    build_followup_draft_graph,
)
from app.api.classification import get_current_user, get_db
from app.api.knowledge import approved_knowledge_scope
from app.db.models import (
    AgentAuditEvent,
    AgentWorkflow,
    Document,
    DocumentClassification,
    DocumentPage,
    ProcurementFollowUp,
    User,
)

router = APIRouter(
    prefix="/agent/workflows",
    tags=["Agent workflows"],
)

class FollowUpDraftRequest(BaseModel):
    document_id: UUID
    instruction: str = Field(min_length=10, max_length=500)

class WorkflowCreate(BaseModel):
    document_id: UUID
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=2000)


class WorkflowDecision(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=500)


def manager_role(user: User) -> bool:
    role = getattr(user.role, "value", user.role)
    return str(role).lower() in {"admin", "manager"}


def authorised_purchase_order(
    db: Session,
    user: User,
    document_id: UUID,
):
    return db.scalar(
        select(Document)
        .join(
            DocumentClassification,
            DocumentClassification.document_id == Document.id,
        )
        .where(
            Document.id == document_id,
            DocumentClassification.predicted_type == "purchase_order",
            approved_knowledge_scope(user),
        )
    )


def checkpoint_url(db: Session) -> str:
    return (
        db.get_bind()
        .url.set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def execute_follow_up(
    db: Session,
    user: User,
    workflow_id: UUID,
    reviewer_id: UUID,
):
    workflow = db.scalar(
        select(AgentWorkflow)
        .where(AgentWorkflow.id == workflow_id)
        .with_for_update()
    )

    if workflow is None:
        raise ValueError("Workflow not found")

    # Safe to execute again if LangGraph retries the node.
    if workflow.status == "completed":
        db.commit()
        return

    if (
        workflow.status != "approved"
        or workflow.reviewed_by_id != reviewer_id
        or user.id != reviewer_id
        or not manager_role(user)
    ):
        db.rollback()
        raise PermissionError("Approval is not valid")

    if not authorised_purchase_order(
        db,
        user,
        workflow.document_id,
    ):
        db.rollback()
        raise PermissionError("Document access denied")

    statement = (
        insert(ProcurementFollowUp)
        .values(
            workflow_id=workflow.id,
            document_id=workflow.document_id,
            title=workflow.title,
            description=workflow.description,
        )
        .on_conflict_do_nothing(
            index_elements=["workflow_id"],
        )
        .returning(ProcurementFollowUp.id)
    )

    created_id = db.scalar(statement)

    if created_id is not None:
        db.add(
            AgentAuditEvent(
                workflow_id=workflow.id,
                actor_id=user.id,
                event_type="follow_up_created",
            )
        )

    workflow.status = "completed"
    db.commit()


def workflow_graph(db: Session, user: User, checkpointer):
    return build_approval_graph(
        checkpointer,
        create_follow_up=lambda workflow_id, reviewer_id: (
            execute_follow_up(
                db,
                user,
                UUID(workflow_id),
                UUID(reviewer_id),
            )
        ),
    )


def workflow_result(db: Session, workflow: AgentWorkflow):
    follow_up_id = db.scalar(
        select(ProcurementFollowUp.id).where(
            ProcurementFollowUp.workflow_id == workflow.id
        )
    )

    return {
        "workflow_id": workflow.id,
        "status": workflow.status,
        "document_id": workflow.document_id,
        "title": workflow.title,
        "description": workflow.description,
        "requested_by_id": workflow.requested_by_id,
        "reviewed_by_id": workflow.reviewed_by_id,
        "review_comment": workflow.review_comment,
        "created_at": workflow.created_at,
        "follow_up_id": follow_up_id,
    }


@router.post("")
def create_workflow(
    payload: WorkflowCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if not authorised_purchase_order(
        db,
        user,
        payload.document_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Approved purchase order not accessible",
        )

    workflow = AgentWorkflow(
        document_id=payload.document_id,
        requested_by_id=user.id,
        title=payload.title,
        description=payload.description,
        status="pending",
    )

    db.add(workflow)
    db.flush()

    db.add(
        AgentAuditEvent(
            workflow_id=workflow.id,
            actor_id=user.id,
            event_type="proposed",
        )
    )

    db.commit()

    config = {
        "configurable": {
            "thread_id": str(workflow.id),
        }
    }

    with PostgresSaver.from_conn_string(
        checkpoint_url(db)
    ) as checkpointer:
        graph = workflow_graph(db, user, checkpointer)

        result = graph.invoke(
            {"workflow_id": str(workflow.id)},
            config=config,
        )

        if "__interrupt__" not in result:
            raise HTTPException(
                status_code=500,
                detail="Approval workflow did not pause",
            )

    return workflow_result(db, workflow)


@router.post("/{workflow_id}/decision")
def decide_workflow(
    workflow_id: UUID,
    payload: WorkflowDecision,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if not manager_role(user):
        raise HTTPException(
            status_code=403,
            detail="Manager approval required",
        )

    workflow = db.scalar(
        select(AgentWorkflow)
        .where(AgentWorkflow.id == workflow_id)
        .with_for_update()
    )

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if workflow.requested_by_id == user.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot approve your own request",
        )

    if not authorised_purchase_order(
        db,
        user,
        workflow.document_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Document access denied",
        )

    desired_status = "approved" if payload.approved else "rejected"

    if workflow.status == "completed":
        if workflow.reviewed_by_id != user.id or not payload.approved:
            raise HTTPException(status_code=409, detail="Already decided")
        db.commit()
        return workflow_result(db, workflow)

    if workflow.status == "pending":
        workflow.status = desired_status
        workflow.reviewed_by_id = user.id
        workflow.review_comment = payload.comment

        db.add(
            AgentAuditEvent(
                workflow_id=workflow.id,
                actor_id=user.id,
                event_type=desired_status,
                details=payload.comment,
            )
        )

        db.commit()

    elif (
        workflow.status != desired_status
        or workflow.reviewed_by_id != user.id
    ):
        raise HTTPException(
            status_code=409,
            detail="Workflow already decided",
        )

    config = {
        "configurable": {
            "thread_id": str(workflow.id),
        }
    }

    with PostgresSaver.from_conn_string(
        checkpoint_url(db)
    ) as checkpointer:
        graph = workflow_graph(db, user, checkpointer)
        snapshot = graph.get_state(config)

        if snapshot.next:
            graph.invoke(
                Command(
                    resume={
                        "approved": payload.approved,
                        "reviewer_id": str(user.id),
                    }
                ),
                config=config,
            )

    db.refresh(workflow)
    return workflow_result(db, workflow)


@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    workflow = db.get(AgentWorkflow, workflow_id)

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not authorised_purchase_order(
        db,
        user,
        workflow.document_id,
    ):
        raise HTTPException(status_code=403, detail="Document access denied")

    if workflow.requested_by_id != user.id and not manager_role(user):
        raise HTTPException(status_code=403, detail="Access denied")

    return workflow_result(db, workflow)

@router.get("")
def list_workflows(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    visible_document_ids = select(Document.id).where(
        approved_knowledge_scope(user)
    )

    query = select(AgentWorkflow).where(
        AgentWorkflow.document_id.in_(visible_document_ids)
    )

    if not manager_role(user):
        query = query.where(
            AgentWorkflow.requested_by_id == user.id
        )

    workflows = db.scalars(
        query.order_by(AgentWorkflow.created_at.desc()).limit(50)
    ).all()

    results = []

    for workflow in workflows:
        record = workflow_result(db, workflow)

        record["can_review"] = (
            manager_role(user)
            and workflow.status == "pending"
            and workflow.requested_by_id != user.id
        )

        results.append(record)

    return results

@router.get("/{workflow_id}/events")
def get_workflow_events(
    workflow_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    workflow = db.get(AgentWorkflow, workflow_id)

    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found",
        )

    if not authorised_purchase_order(
        db,
        user,
        workflow.document_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Document access denied",
        )

    if (
        workflow.requested_by_id != user.id
        and not manager_role(user)
    ):
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    events = db.scalars(
        select(AgentAuditEvent)
        .where(AgentAuditEvent.workflow_id == workflow_id)
        .order_by(AgentAuditEvent.created_at.asc())
    ).all()

    return [
        {
            "event_type": event.event_type,
            "actor_id": event.actor_id,
            "details": event.details,
            "created_at": event.created_at,
        }
        for event in events
    ]

@router.post("/draft")
def draft_follow_up(
    payload: FollowUpDraftRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = authorised_purchase_order(
        db,
        user,
        payload.document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=403,
            detail="Approved purchase order not accessible",
        )

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == payload.document_id)
        .order_by(DocumentPage.page_number)
    ).all()

    graph = build_followup_draft_graph()

    try:
        result = graph.invoke(
            {
                "instruction": payload.instruction,
                "pages": [
                    {
                        "page_number": page.page_number,
                        "text": page.text,
                    }
                    for page in pages
                ],
            }
        )
    except FollowUpDraftError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    proposal = result["proposal"]
    page_number = proposal["evidence_page"]

    return {
        "document_id": payload.document_id,
        "title": proposal["title"],
        "description": proposal["description"],
        "evidence_page": page_number,
        "source_ref": (
            f"document:{payload.document_id}:page:{page_number}"
        ),
        "requires_confirmation": True,
    }