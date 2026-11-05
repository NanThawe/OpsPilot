from evals.run import evaluate_body


DOCUMENT_ID = "5f810213-03e9-45b5-8019-9eb7ca5761e4"


def test_wrong_date_is_detected():
    case = {
        "kind": "agent",
        "expected_action": "first_delivery",
        "expected_tool": "get_delivery_milestones",
        "required_phrases": ["10 Nov 2026"],
        "evidence_page": 2,
    }

    response = {
        "action": "first_delivery",
        "tool_used": "get_delivery_milestones",
        "answer": "24 Nov 2026",
        "citations": [
            {
                "document_id": DOCUMENT_ID,
                "page_number": 2,
            }
        ],
    }

    issues = evaluate_body(case, response, DOCUMENT_ID)

    assert any("10 Nov 2026" in issue for issue in issues)


def test_correct_delivery_passes():
    case = {
        "kind": "agent",
        "expected_action": "first_delivery",
        "expected_tool": "get_delivery_milestones",
        "required_phrases": ["10 Nov 2026"],
        "evidence_page": 2,
    }

    response = {
        "action": "first_delivery",
        "tool_used": "get_delivery_milestones",
        "answer": "Batch A: 10 Nov 2026",
        "citations": [
            {
                "document_id": DOCUMENT_ID,
                "page_number": 2,
            }
        ],
    }

    assert evaluate_body(case, response, DOCUMENT_ID) == []


def test_unsupported_answer_with_citation_fails():
    case = {
        "kind": "rag",
        "expected_supported": False,
        "required_phrases": [],
    }

    response = {
        "supported": False,
        "answer": "I cannot confirm the bank account.",
        "citations": [{"page_number": 1}],
    }

    issues = evaluate_body(case, response, DOCUMENT_ID)

    assert "unsupported answer contains citations" in issues