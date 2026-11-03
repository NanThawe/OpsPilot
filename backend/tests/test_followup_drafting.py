import pytest

from app.agents.followup_drafting import (
    FollowUpDraftError,
    prepare_context,
    verify_draft,
)


def test_prepare_context():
    result = prepare_context(
        {
            "pages": [
                {
                    "page_number": 2,
                    "text": "Batch A: 10 Nov 2026",
                }
            ]
        }
    )

    assert "[PAGE 2]" in result["context"]
    assert "10 Nov 2026" in result["context"]


def test_invalid_evidence_page():
    with pytest.raises(
        FollowUpDraftError,
        match="invalid evidence page",
    ):
        verify_draft(
            {
                "pages": [
                    {
                        "page_number": 1,
                        "text": "Purchase order",
                    }
                ],
                "proposal": {
                    "title": "Confirm delivery",
                    "description": "Contact supplier",
                    "evidence_page": 99,
                },
            }
        )