from __future__ import annotations

import csv
import sys

from src.db import Database
from src.settings import load_settings


def main() -> None:
    settings = load_settings()
    db = Database(settings.database_path)
    rows = db.approved_items_for_csv()
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "receipt_id",
            "created_at",
            "discord_user_id",
            "version_number",
            "name",
            "original_name",
            "category",
            "quantity",
            "unit",
            "unit_price",
            "total_price",
            "currency",
            "confidence",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
