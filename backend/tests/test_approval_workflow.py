from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.approval_workflow import build_approval_graph


def test_approval_creates_follow_up():
    actions = []

    graph = build_approval_graph(
        InMemorySaver(),
        lambda workflow_id, reviewer_id: actions.append(
            (workflow_id, reviewer_id)
        ),
    )

    config = {"configurable": {"thread_id": "approval-test-1"}}

    paused = graph.invoke(
        {"workflow_id": "workflow-1"},
        config=config,
    )

    assert "__interrupt__" in paused
    assert actions == []

    result = graph.invoke(
        Command(
            resume={
                "approved": True,
                "reviewer_id": "manager-1",
            }
        ),
        config=config,
    )

    assert result["status"] == "completed"
    assert actions == [("workflow-1", "manager-1")]


def test_rejection_does_not_create_follow_up():
    actions = []

    graph = build_approval_graph(
        InMemorySaver(),
        lambda workflow_id, reviewer_id: actions.append(
            (workflow_id, reviewer_id)
        ),
    )

    config = {"configurable": {"thread_id": "approval-test-2"}}

    graph.invoke(
        {"workflow_id": "workflow-2"},
        config=config,
    )

    result = graph.invoke(
        Command(
            resume={
                "approved": False,
                "reviewer_id": "manager-1",
            }
        ),
        config=config,
    )

    assert result["status"] == "rejected"
    assert actions == []