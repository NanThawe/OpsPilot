from types import SimpleNamespace

from app.services import purchase_orders as service
from app.services.purchase_orders import (
    PurchaseOrderLine,
    PurchaseOrderProposal,
    reconcile_purchase_order_from_source,
    resolve_source_pages,
    validate_purchase_order,
)


def test_two_page_document_references():
    pages = [
        SimpleNamespace(
            page_number=1,
            text="Purchase Order PO-002",
        ),
        SimpleNamespace(
            page_number=2,
            text="Rugged equipment delivery",
        ),
    ]

    proposal = PurchaseOrderProposal(
        po_number="PO-002",
        line_items=[
            PurchaseOrderLine(
                description="Rugged equipment delivery",
                quantity="2",
                unit_price="100.00",
                printed_line_total="200.00",
                page_number=0,
            )
        ],
        total_amount="200.00",
        evidence_page_numbers=[0, 3],
    )

    result = resolve_source_pages(proposal, pages)

    assert result.evidence_page_numbers == [1, 2]
    assert result.line_items[0].page_number == 2


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

    issue = next(issue for issue in result.issues if issue.code == "total_mismatch")

    assert issue.expected == "1635.00"
    assert issue.stated == "1625.00"


def test_wrong_line_item_total_is_flagged():
    proposal = make_purchase_order()
    proposal.line_items[1].printed_line_total = "625.00"

    result = validate_purchase_order(proposal)

    assert result.status == "flagged"
    assert any(issue.code == "line_amount_mismatch" for issue in result.issues)


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
    assert captured["format"] == (PurchaseOrderProposal.model_json_schema())


from app.services.purchase_orders import (
    parse_flattened_ordered_items,
)


def test_po003_discrepancy_from_pdf_text():
    text = """
ORDERED ITEMS
ITEM CODE
DESCRIPTION
QTY
UNIT (SGD)
AMOUNT
SAFE-HELM
Protective safety helmet
20
36.00
720.00
SAFE-VEST
High-visibility vest
25
18.00
450.00
SAFE-GLVE
Safety gloves (box)
12
27.50
330.00
Subtotal
1,500.00
GST (9%)
135.00
TOTAL PAYABLE (SGD)
1,625.00
"""

    items = parse_flattened_ordered_items(text, 1)

    assert len(items) == 3

    proposal = PurchaseOrderProposal(
        po_number="PO-SYN-2026-003",
        currency="SGD",
        line_items=items,
        subtotal="1500.00",
        tax_amount="135.00",
        total_amount="1625.00",
        evidence_page_numbers=[1],
    )

    result = validate_purchase_order(proposal)

    assert result.status == "flagged"
    assert result.calculated_total == "1635.00"

    assert any(
        issue.code == "total_mismatch"
        and issue.expected == "1635.00"
        and issue.stated == "1625.00"
        for issue in result.issues
    )


def test_two_page_purchase_order_extracts_correctly():
    page_one = """
PURCHASE ORDER
PO NUMBER
PO-SYN-2026-002
CURRENCY
SGD
BUYER / BILL TO
Harborlane Facilities
SUPPLIER
Pinecrest Industrial Materials
ORDERED ITEMS
ITEM CODE
DESCRIPTION
QTY
UNIT (SGD)
AMOUNT
OPS-SCAN
Portable barcode scanner
15
235.00
3,525.00
OPS-PRNT
Rugged thermal label printer
6
468.00
2,808.00
OPS-LABL
Thermal label roll (carton)
20
39.00
780.00
OPS-BATT
Spare battery pack
12
68.00
816.00
Subtotal
7,929.00
Volume discount (5%)
-396.45
Taxable base
7,532.55
GST (9%)
677.93
TOTAL PAYABLE (SGD)
8,210.48
"""

    page_two = """
DELIVERY TERMS
STAGED DELIVERY SCHEDULE
MILESTONE
DUE
DELIVERABLES
Batch A
10 Nov 2026
10 scanners; 3 label printers
10 cartons thermal labels
Batch B
24 Nov 2026
5 scanners; 3 label printers
10 label cartons; 12 battery packs
DELIVERY LOCATION AND RECEIVING RULES
"""

    pages = [
        SimpleNamespace(
            page_number=1,
            text=page_one,
        ),
        SimpleNamespace(
            page_number=2,
            text=page_two,
        ),
    ]

    proposal = PurchaseOrderProposal(
        po_number="PO-SYN-2026-002",
        vendor="Incorrect supplier details",
        line_items=[],
        evidence_page_numbers=[0],
    )

    result = reconcile_purchase_order_from_source(
        proposal,
        pages,
    )

    result = resolve_source_pages(result, pages)

    validation = validate_purchase_order(result)

    assert result.vendor == "Pinecrest Industrial Materials"
    assert result.buyer == "Harborlane Facilities"
    assert result.currency == "SGD"

    assert len(result.line_items) == 4
    assert result.subtotal == "7929.00"
    assert result.discount_amount == "396.45"
    assert result.tax_amount == "677.93"
    assert result.total_amount == "8210.48"

    assert len(result.delivery_milestones) == 2
    assert result.delivery_milestones[0].name == "Batch A"
    assert result.delivery_milestones[1].name == "Batch B"

    assert result.evidence_page_numbers == [1, 2]

    assert validation.status == "passed"
    assert validation.calculated_total == "8210.48"
    assert validation.issues == []
