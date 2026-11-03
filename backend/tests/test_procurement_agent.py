from app.agents.procurement import (
    route_action,
    select_delivery_milestone,
)

MILESTONES = [
    {
        "name": "Batch A",
        "due_date": "10 Nov 2026",
        "deliverables": "10 scanners",
        "page_number": 2,
    },
    {
        "name": "Batch B",
        "due_date": "24 Nov 2026",
        "deliverables": "5 scanners",
        "page_number": 2,
    },
]


def test_first_delivery_selection():
    result = select_delivery_milestone(
        MILESTONES,
        first=True,
    )

    assert result["name"] == "Batch A"
    assert result["due_date"] == "10 Nov 2026"


def test_final_delivery_selection():
    result = select_delivery_milestone(
        MILESTONES,
        first=False,
    )

    assert result["name"] == "Batch B"
    assert result["due_date"] == "24 Nov 2026"


def test_delivery_routing():
    state = {
        "question": "When is the first delivery?",
        "action": "first_delivery",
    }

    assert route_action(state) == "delivery"


def test_knowledge_routing():
    state = {
        "question": "What are the payment terms?",
        "action": "knowledge",
    }

    assert route_action(state) == "knowledge"


def test_unsupported_action():
    state = {
        "question": "Send an email",
        "action": "unsupported",
    }

    assert route_action(state) == "clarify"