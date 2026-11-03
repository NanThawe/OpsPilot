from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class ApprovalState(TypedDict, total=False):
    workflow_id: str
    approved: bool
    reviewer_id: str
    status: str


def build_approval_graph(
    checkpointer,
    create_follow_up: Callable[[str, str], None],
):
    def human_review(state: ApprovalState):
        decision = interrupt(
            {
                "action": "create_procurement_follow_up",
                "workflow_id": state["workflow_id"],
                "message": "Manager approval required",
            }
        )

        approved = decision["approved"] is True

        return {
            "approved": approved,
            "reviewer_id": decision["reviewer_id"],
            "status": "approved" if approved else "rejected",
        }

    def route_decision(state: ApprovalState):
        return "execute" if state["approved"] else "end"

    def execute_action(state: ApprovalState):
        create_follow_up(
            state["workflow_id"],
            state["reviewer_id"],
        )

        return {"status": "completed"}

    builder = StateGraph(ApprovalState)

    builder.add_node("human_review", human_review)
    builder.add_node("execute_action", execute_action)

    builder.add_edge(START, "human_review")

    builder.add_conditional_edges(
        "human_review",
        route_decision,
        {
            "execute": "execute_action",
            "end": END,
        },
    )

    builder.add_edge("execute_action", END)

    return builder.compile(checkpointer=checkpointer)