from __future__ import annotations

from src.formatting import format_receipt_summary
from src.models import ExpenseCategory, ParsedReceipt, ReceiptItem, ReceiptTotals


def test_format_receipt_summary_includes_items_and_approval_hint() -> None:
    parsed = ParsedReceipt(
        merchant_name="Lotus",
        merchant_address=None,
        receipt_date=None,
        language="mixed",
        currency="THB",
        items=[
            ReceiptItem(
                name="Rice",
                original_name="ข้าว",
                category=ExpenseCategory.GROCERIES,
                quantity=1,
                unit="bag",
                unit_price=120,
                total_price=120,
                confidence=0.95,
            )
        ],
        totals=ReceiptTotals(total=120, currency="THB"),
        payment_method=None,
        receipt_number=None,
        overall_confidence=0.9,
    )

    text = format_receipt_summary(parsed, receipt_id=1, version_id=2)

    assert "Lotus" in text
    assert "Rice" in text
    assert "groceries" in text
    assert "Approve to save" in text
