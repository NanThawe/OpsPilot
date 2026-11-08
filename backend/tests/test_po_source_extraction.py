"""Regression tests for text-based purchase order extraction."""

from types import SimpleNamespace

import pytest

from app.services import purchase_orders


@pytest.fixture(autouse=True)
def no_llm_needed(monkeypatch):
    """Recognised templates must not require Ollama to be available."""

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Complete source text should bypass Ollama")

    monkeypatch.setattr(purchase_orders, "OllamaClient", fail_if_called)


def _extract(text: str, *, page_number: int = 1):
    page = SimpleNamespace(text=text, page_number=page_number)
    proposal = purchase_orders.extract_purchase_order([page])
    return proposal, purchase_orders.validate_purchase_order(proposal)


FINAL_DEMO = """PURCHASE ORDER
PO Number: PO-DEMO-2026-001
Issue Date: 07 Nov 2026
Currency: SGD
Buyer
Eastvale Project Services
Supplier
Pinecrest Industrial Materials
Supplier ID: SYN-SUP-118
LINE ITEMS
Item
Quantity
Unit Price
Printed Amount
DEMO-SCAN: Mobile barcode scanner
8
420.00
3,360.00
DEMO-PRNT: Industrial label printer
4
610.00
2,440.00
DEMO-BATT: Spare battery pack
12
95.00
1,140.00
Subtotal: SGD 6,940.00
GST (9%): SGD 624.60
Grand Total: SGD 7,564.60
"""


FLATTENED = """PURCHASE ORDER
PO NUMBER
PO-DEMO-2026-001
CURRENCY
SGD
BUYER / BILL TO
Harborlane Facilities Group
SUPPLIER
Pinecrest Industrial Materials (SYN-SUP-401)
ORDERED ITEMS
ITEM CODE
DESCRIPTION
QTY
UNIT (SGD)
AMOUNT
DEMO-SCAN
Mobile barcode scanner
8
420.00
3,360.00
DEMO-PRNT
Industrial label printer
4
610.00
2,440.00
DEMO-BATT
Spare battery pack
12
95.00
1,140.00
Subtotal
6,940.00
GST (9%)
624.60
TOTAL
PAYABLE
(SGD)
7,564.60
"""


def test_inline_demo_pdf_extracts_and_passes():
    proposal, validation = _extract(FINAL_DEMO)
    assert proposal.po_number == "PO-DEMO-2026-001"
    assert proposal.vendor == "Pinecrest Industrial Materials"
    assert proposal.currency == "SGD"
    assert len(proposal.line_items) == 3
    assert proposal.tax_amount == "624.60"
    assert proposal.total_amount == "7564.60"
    assert validation.status == "passed"
    assert validation.calculated_total == "7564.60"
    assert proposal.evidence_page_numbers == [1]


def test_flattened_pdf_and_split_total_are_supported():
    proposal, validation = _extract(FLATTENED)
    assert proposal.vendor == "Pinecrest Industrial Materials"
    assert len(proposal.line_items) == 3
    assert proposal.total_amount == "7564.60"
    assert validation.status == "passed"


def test_wrong_printed_total_stays_flagged():
    text = FINAL_DEMO.replace("Grand Total: SGD 7,564.60", "Grand Total: SGD 7,549.60")
    proposal, validation = _extract(text)
    assert proposal.total_amount == "7549.60"
    assert validation.status == "flagged"
    assert any(issue.code == "total_mismatch" for issue in validation.issues)
    assert validation.calculated_total == "7564.60"


def test_missing_lines_remains_needs_review():
    proposal = purchase_orders.PurchaseOrderProposal(
        po_number="PO-TEST-001", total_amount="100.00"
    )
    validation = purchase_orders.validate_purchase_order(proposal)
    assert validation.status == "needs_review"
    assert validation.issues[0].code == "missing_line_items"


def test_discount_is_subtracted_without_fixing_printed_total():
    text = FLATTENED.replace(
        "GST (9%)\n624.60",
        "Volume discount\n-100.00\nGST (9%)\n615.60",
    ).replace("7,564.60", "7,455.60")
    proposal, validation = _extract(text)
    assert proposal.discount_amount == "100.00"
    assert proposal.tax_amount == "615.60"
    assert validation.calculated_total == "7455.60"
    assert validation.status == "passed"
