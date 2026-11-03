from datetime import datetime
from typing import Any, Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from ollama import Client, ResponseError
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.knowledge import (
    AskRequest,
    approved_knowledge_scope,
    ask_documents,
)
from app.core.config import settings
from app.db.models import (
    Document,
    DocumentClassification,
    PurchaseOrderExtraction,
    User,
)


class ProcurementAgentError(Exception):
    pass


class AgentPlan(BaseModel):
    action: Literal[
        "summary",
        "first_delivery",
        "final_delivery",
        "delivery_schedule",
        "knowledge",
        "clarify",
    ]
    po_number: str | None = None


class AgentState(TypedDict, total=False):
    question: str
    action: str
    po_number: str | None
    answer: str
    tool_used: str
    citations: list[dict[str, Any]]


PLANNING_PROMPT = """
You are a procurement task planner for OpsPilot.

Select exactly one action:

summary:
The user wants basic purchase order information,
including supplier, buyer, currency or total amount.

first_delivery:
The user asks for the first or earliest scheduled delivery.

final_delivery:
The user asks for the final or latest delivery milestone.

delivery_schedule:
The user asks about multiple batches or delivery schedules.

knowledge:
The user asks about document policies, payment conditions,
receiving rules or other information requiring document search.

clarify:
The request is unclear, requires missing information,
or asks for an action not supported by this read-only agent.

Extract the purchase order number if explicitly provided.

Never invent a purchase order number.

Requests to send emails, approve purchase orders,
modify records, or create tasks must use clarify.

Return JSON matching the provided schema.
"""

def plan_request(question: str) -> AgentPlan:
    try:
        client = Client(
            host=settings.ollama_base_url,
            timeout=180.0,
        )

        response = client.chat(
            model=settings.ollama_model,
            messages=[
                {
                    "role": "system",
                    "content": PLANNING_PROMPT,
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            format=AgentPlan.model_json_schema(),
            options={"temperature": 0},
        )

        return AgentPlan.model_validate_json(
            response.message.content or ""
        )

    except (
        ResponseError,
        httpx.HTTPError,
        ValidationError,
    ) as exc:
        raise ProcurementAgentError(
            "Agent planning failed"
        ) from exc

def get_authorised_purchase_order(
    db: Session,
    user: User,
    po_number: str,
):
    statement = (
        select(
            Document,
            PurchaseOrderExtraction,
        )
        .join(
            DocumentClassification,
            DocumentClassification.document_id == Document.id,
        )
        .join(
            PurchaseOrderExtraction,
            PurchaseOrderExtraction.document_id == Document.id,
        )
        .where(
            approved_knowledge_scope(user),
            DocumentClassification.predicted_type
            == "purchase_order",
        )
        .order_by(Document.created_at.desc())
    )

    for document, extraction in db.execute(statement):
        extracted_number = extraction.extracted_data.get(
            "po_number"
        )

        if (
            isinstance(extracted_number, str)
            and extracted_number.casefold() == po_number.casefold()
        ):
            return document, extraction

    return None

def select_delivery_milestone(
    milestones: list[dict],
    *,
    first: bool,
) -> dict:
    if not milestones:
        raise ValueError("No delivery milestones available")

    return sorted(
        milestones,
        key=lambda item: datetime.strptime(
            item["due_date"],
            "%d %b %Y",
        ),
        reverse=not first,
    )[0]

def route_action(state: AgentState) -> str:
    action = state.get("action")

    if action == "summary":
        return "summary"

    if action in {
        "first_delivery",
        "final_delivery",
        "delivery_schedule",
    }:
        return "delivery"

    if action == "knowledge":
        return "knowledge"

    return "clarify"

def run_procurement_agent(
    question: str,
    db: Session,
    user: User,
) -> AgentState:

    def planning_node(state: AgentState) -> dict:
        plan = plan_request(state["question"])

        # Do not accept invented document identifiers.
        if (
            plan.po_number
            and plan.po_number.casefold()
            not in state["question"].casefold()
        ):
            return {
                "action": "clarify",
                "po_number": None,
            }

        return {
            "action": plan.action,
            "po_number": plan.po_number,
        }

    def summary_node(state: AgentState) -> dict:
        po_number = state.get("po_number")

        if not po_number:
            return {
                "answer": "Please specify a purchase order number.",
                "tool_used": "get_purchase_order",
                "citations": [],
            }

        record = get_authorised_purchase_order(
            db,
            user,
            po_number,
        )

        if record is None:
            return {
                "answer": (
                    "I could not find an approved purchase order "
                    "accessible to your account."
                ),
                "tool_used": "get_purchase_order",
                "citations": [],
            }

        document, extraction = record
        data = extraction.extracted_data

        answer = (
            f"Purchase order: {data.get('po_number')}\n"
            f"Supplier: {data.get('vendor')}\n"
            f"Buyer: {data.get('buyer')}\n"
            f"Currency: {data.get('currency')}\n"
            f"Total: {data.get('total_amount')}\n"
            f"Validation: {extraction.validation_status}"
        )

        return {
            "answer": answer,
            "tool_used": "get_purchase_order",
            "citations": [
                {
                    "document_id": str(document.id),
                    "document_title": document.title,
                    "page_number": 1,
                    "source_ref": (
                        f"document:{document.id}:page:1"
                    ),
                }
            ],
        }

    def delivery_node(state: AgentState) -> dict:
        po_number = state.get("po_number")

        if not po_number:
            return {
                "answer": "Please specify a purchase order number.",
                "tool_used": "get_delivery_milestones",
                "citations": [],
            }

        record = get_authorised_purchase_order(
            db,
            user,
            po_number,
        )

        if record is None:
            return {
                "answer": (
                    "I could not find an approved purchase order "
                    "accessible to your account."
                ),
                "tool_used": "get_delivery_milestones",
                "citations": [],
            }

        document, extraction = record

        milestones = extraction.extracted_data.get(
            "delivery_milestones",
            [],
        )

        if not milestones:
            return {
                "answer": "No delivery milestones were extracted.",
                "tool_used": "get_delivery_milestones",
                "citations": [],
            }

        action = state["action"]

        try:
            if action == "first_delivery":
                selected = [
                    select_delivery_milestone(
                        milestones,
                        first=True,
                    )
                ]

            elif action == "final_delivery":
                selected = [
                    select_delivery_milestone(
                        milestones,
                        first=False,
                    )
                ]

            else:
                selected = sorted(
                    milestones,
                    key=lambda item: datetime.strptime(
                        item["due_date"],
                        "%d %b %Y",
                    ),
                )

        except (ValueError, KeyError, TypeError):
            return {
                "answer": (
                    "The delivery milestone data could not "
                    "be validated."
                ),
                "tool_used": "get_delivery_milestones",
                "citations": [],
            }

        answer = "\n".join(
            (
                f"{item['name']}: {item['due_date']}. "
                f"Deliverables: {item['deliverables']}"
            )
            for item in selected
        )

        citations = []

        for item in selected:
            page_number = item["page_number"]

            citations.append(
                {
                    "document_id": str(document.id),
                    "document_title": document.title,
                    "page_number": page_number,
                    "source_ref": (
                        f"document:{document.id}:"
                        f"page:{page_number}"
                    ),
                }
            )

        return {
            "answer": answer,
            "tool_used": "get_delivery_milestones",
            "citations": citations,
        }

    def knowledge_node(state: AgentState) -> dict:
        response = ask_documents(
            payload=AskRequest(
                question=state["question"]
            ),
            db=db,
            user=user,
        )

        return {
            "answer": response.answer,
            "tool_used": "search_company_knowledge",
            "citations": [
                citation.model_dump(mode="json")
                for citation in response.citations
            ],
        }

    def clarify_node(state: AgentState) -> dict:
        return {
            "answer": (
                "I can retrieve approved purchase orders, "
                "check delivery milestones, and answer "
                "questions about company documents. "
                "Please provide a specific request and "
                "purchase order number where applicable."
            ),
            "tool_used": "none",
            "citations": [],
        }

    builder = StateGraph(AgentState)

    builder.add_node("plan", planning_node)
    builder.add_node("summary", summary_node)
    builder.add_node("delivery", delivery_node)
    builder.add_node("knowledge", knowledge_node)
    builder.add_node("clarify", clarify_node)

    builder.add_edge(START, "plan")

    builder.add_conditional_edges(
        "plan",
        route_action,
        {
            "summary": "summary",
            "delivery": "delivery",
            "knowledge": "knowledge",
            "clarify": "clarify",
        },
    )

    builder.add_edge("summary", END)
    builder.add_edge("delivery", END)
    builder.add_edge("knowledge", END)
    builder.add_edge("clarify", END)

    graph = builder.compile()

    result = graph.invoke(
        {"question": question}
    )

    return result