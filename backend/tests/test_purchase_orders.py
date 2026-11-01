from types import SimpleNamespace

from app.services import purchase_orders as service
from app.services.purchase_orders import (
    PurchaseOrderLine,
    PurchaseOrderProposal,
    validate_purchase_order,
)


def make_purchase_order(
    total: str | None = "1635.00",
) -> PurchaseOrderProposal:
    return PurchaseOrderProposal(
        po_number="PO-SYN-2026-TEST",
        vendor="Synthetic Supplier",
        buyer="Demo Company",
        currency="SGD",
        line_items=[
            PurchaseOrderLine(
                description="Equipment A",
                quantity="1",
                unit_price="1000.00",
                printed_line_total="1000.00",
                page_number=1,
            ),
            PurchaseOrderLine(
                description="Equipment B",
                quantity="1",
                unit_price="635.00",
                printed_line_total="635.00",
                page_number=1,
            ),
        ],
        subtotal="1635.00",
        tax_amount="0.00",
        shipping_amount="0.00",
        discount_amount="0.00",
        total_amount=total,
        evidence_page_numbers=[1],
    )


def test_correct_purchase_order_passes():
    proposal = make_purchase_order()

    result = validate_purchase_order(proposal)

    assert result.status == "passed"
    assert result.calculated_total == "1635.00"
    assert result.issues == []


def test_ten_dollar_discrepancy_is_flagged():
    proposal = make_purchase_order(total="1625.00")

    result = validate_purchase_order(proposal)

    assert result.status == "flagged"
    assert result.calculated_total == "1635.00"

    issue = next(
        issue
        for issue in result.issues
        if issue.code == "total_mismatch"
    )

    assert issue.expected == "1635.00"
    assert issue.stated == "1625.00"


def test_wrong_line_item_total_is_flagged():
    proposal = make_purchase_order()
    proposal.line_items[1].printed_line_total = "625.00"

    result = validate_purchase_order(proposal)

    assert result.status == "flagged"
    assert any(
        issue.code == "line_amount_mismatch"
        for issue in result.issues
    )


def test_missing_grand_total_needs_review():
    proposal = make_purchase_order(total=None)

    result = validate_purchase_order(proposal)

    assert result.status == "needs_review"


def test_no_line_items_needs_review():
    proposal = make_purchase_order()
    proposal.line_items = []

    result = validate_purchase_order(proposal)

    assert result.status == "needs_review"


def test_ollama_extracts_structured_purchase_order(monkeypatch):
    expected = make_purchase_order()
    captured = {}

    class FakeClient:
        def chat(self, **kwargs):
            captured.update(kwargs)

            return SimpleNamespace(
                message=SimpleNamespace(
                    content=expected.model_dump_json(),
                )
            )

    monkeypatch.setattr(
        service,
        "OllamaClient",
        lambda **kwargs: FakeClient(),
    )

    pages = [
        SimpleNamespace(
            page_number=1,
            text="Purchase order PO-SYN-2026-TEST",
        )
    ]

    result = service.extract_purchase_order(pages)

    assert result.po_number == "PO-SYN-2026-TEST"
    assert result.total_amount == "1635.00"
    assert captured["format"] == (
        PurchaseOrderProposal.model_json_schema()
    )