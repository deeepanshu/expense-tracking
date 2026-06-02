from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter

from src.models import ParsedReceipt


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self) -> None:
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS receipts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              discord_message_id TEXT NOT NULL UNIQUE,
              discord_channel_id TEXT NOT NULL,
              discord_user_id TEXT NOT NULL,
              image_path TEXT NOT NULL,
              image_content_type TEXT,
              status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected')),
              active_version_id INTEGER,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              approved_at TEXT,
              rejected_at TEXT
            );

            CREATE TABLE IF NOT EXISTS receipt_versions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
              version_number INTEGER NOT NULL,
              source TEXT NOT NULL CHECK (source IN ('ai','user_correction')),
              status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected')),
              parsed_json TEXT NOT NULL,
              raw_model_output TEXT,
              correction_note TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(receipt_id, version_number)
            );

            CREATE TABLE IF NOT EXISTS items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
              version_id INTEGER NOT NULL REFERENCES receipt_versions(id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              original_name TEXT,
              category TEXT NOT NULL,
              quantity REAL,
              unit TEXT,
              unit_price REAL,
              total_price REAL NOT NULL,
              currency TEXT NOT NULL,
              confidence REAL NOT NULL,
              notes TEXT
            );
            """
        )
        self.conn.commit()

    def create_receipt(
        self,
        *,
        discord_message_id: str,
        discord_channel_id: str,
        discord_user_id: str,
        image_path: Path,
        image_content_type: str | None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO receipts (
              discord_message_id, discord_channel_id, discord_user_id,
              image_path, image_content_type, status
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (
                discord_message_id,
                discord_channel_id,
                discord_user_id,
                str(image_path),
                image_content_type,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a receipt id")
        receipt_id = cursor.lastrowid
        self.conn.commit()
        return receipt_id

    def add_version(
        self,
        *,
        receipt_id: int,
        parsed: ParsedReceipt,
        raw_model_output: str | None,
        source: Literal["ai", "user_correction"] = "ai",
        correction_note: str | None = None,
    ) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM receipt_versions WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        version_number = int(row["next_version"])
        cursor = self.conn.execute(
            """
            INSERT INTO receipt_versions (
              receipt_id, version_number, source, status, parsed_json, raw_model_output, correction_note
            ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                receipt_id,
                version_number,
                source,
                parsed.model_dump_json(),
                raw_model_output,
                correction_note,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a version id")
        version_id = cursor.lastrowid
        self.conn.execute("UPDATE receipts SET active_version_id = ? WHERE id = ?", (version_id, receipt_id))
        self.conn.commit()
        return version_id

    def approve_version(self, version_id: int) -> None:
        row = self.conn.execute(
            "SELECT receipt_id, parsed_json FROM receipt_versions WHERE id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No receipt version found for id {version_id}")

        receipt_id = int(row["receipt_id"])
        parsed = ParsedReceipt.model_validate_json(str(row["parsed_json"]))
        with self.conn:
            self.conn.execute(
                "UPDATE receipt_versions SET status = 'rejected' WHERE receipt_id = ?",
                (receipt_id,),
            )
            self.conn.execute("UPDATE receipt_versions SET status = 'approved' WHERE id = ?", (version_id,))
            self.conn.execute(
                """
                UPDATE receipts
                SET status = 'approved', active_version_id = ?, approved_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (version_id, receipt_id),
            )
            self.conn.execute("DELETE FROM items WHERE receipt_id = ?", (receipt_id,))
            for item in parsed.items:
                self.conn.execute(
                    """
                    INSERT INTO items (
                      receipt_id, version_id, name, original_name, category, quantity, unit,
                      unit_price, total_price, currency, confidence, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt_id,
                        version_id,
                        item.name,
                        item.original_name,
                        item.category.value,
                        item.quantity,
                        item.unit,
                        item.unit_price,
                        item.total_price,
                        item.currency or parsed.currency,
                        item.confidence,
                        item.notes,
                    ),
                )

    def reject_receipt(self, version_id: int) -> None:
        row = self.conn.execute(
            "SELECT receipt_id FROM receipt_versions WHERE id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No receipt version found for id {version_id}")
        receipt_id = int(row["receipt_id"])
        with self.conn:
            self.conn.execute("UPDATE receipt_versions SET status = 'rejected' WHERE id = ?", (version_id,))
            self.conn.execute(
                "UPDATE receipts SET status = 'rejected', rejected_at = CURRENT_TIMESTAMP WHERE id = ?",
                (receipt_id,),
            )

    def approved_items_for_csv(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT r.id AS receipt_id, r.created_at, r.discord_user_id, rv.version_number,
                   i.name, i.original_name, i.category, i.quantity, i.unit, i.unit_price,
                   i.total_price, i.currency, i.confidence
            FROM items i
            JOIN receipts r ON r.id = i.receipt_id
            JOIN receipt_versions rv ON rv.id = i.version_id
            WHERE r.status = 'approved'
            ORDER BY r.created_at DESC, i.id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_parsed(self, version_id: int) -> ParsedReceipt:
        row = self.conn.execute(
            "SELECT parsed_json FROM receipt_versions WHERE id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No receipt version found for id {version_id}")
        return TypeAdapter(ParsedReceipt).validate_python(json.loads(str(row["parsed_json"])))
