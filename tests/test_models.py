from __future__ import annotations

from src.models import ExpenseCategory, ParsedReceipt, ReceiptItem, ReceiptTotals


def test_defaults_item_currency_and_detects_total_mismatch() -> None:
    parsed = ParsedReceipt(
        merchant_name="Test Shop",
        merchant_address=None,
        receipt_date=None,
        language="en",
        currency="thb",
        items=[
            ReceiptItem(
                name="Milk",
                category=ExpenseCategory.GROCERIES,
                quantity=1,
                unit="bottle",
                unit_price=30,
                total_price=30,
                confidence=0.9,
            )
        ],
        totals=ReceiptTotals(total=40),
        payment_method=None,
        receipt_number=None,
        issues=[],
        overall_confidence=0.8,
    )

    assert parsed.currency == "THB"
    assert parsed.items[0].currency == "THB"
    assert parsed.issues
    assert parsed.issues[0].needs_user_clarification is True


def test_basic_categories_exist() -> None:
    assert ExpenseCategory.GROCERIES.value == "groceries"
    assert ExpenseCategory.RESTAURANT.value == "restaurant"
    assert ExpenseCategory.OTHER.value == "other"
