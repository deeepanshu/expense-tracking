from __future__ import annotations

from pathlib import Path

from src.db import Database
from src.models import ExpenseCategory, ParsedReceipt, ReceiptItem, ReceiptTotals


def parsed_receipt() -> ParsedReceipt:
    return ParsedReceipt(
        merchant_name="Test Shop",
        merchant_address=None,
        receipt_date=None,
        language="en",
        currency="THB",
        items=[
            ReceiptItem(
                name="Coffee",
                category=ExpenseCategory.CAFE,
                quantity=1,
                unit="cup",
                unit_price=65,
                total_price=65,
                confidence=0.95,
            )
        ],
        totals=ReceiptTotals(total=65, currency="THB"),
        payment_method=None,
        receipt_number=None,
        overall_confidence=0.9,
    )


def test_database_uses_versioned_receipts_and_exports_approved_items(tmp_path: Path) -> None:
    db = Database(tmp_path / "expenses.sqlite")
    receipt_id = db.create_receipt(
        discord_message_id="message-1",
        discord_channel_id="channel-1",
        discord_user_id="user-1",
        image_path=tmp_path / "receipt.jpg",
        image_content_type="image/jpeg",
    )
    version_id = db.add_version(receipt_id=receipt_id, parsed=parsed_receipt(), raw_model_output='{"ok":true}')

    db.approve_version(version_id)

    rows = db.approved_items_for_csv()
    assert len(rows) == 1
    assert rows[0]["receipt_id"] == receipt_id
    assert rows[0]["version_number"] == 1
    assert rows[0]["name"] == "Coffee"
    assert rows[0]["category"] == "cafe"
    assert db.latest_parsed(version_id).merchant_name == "Test Shop"
