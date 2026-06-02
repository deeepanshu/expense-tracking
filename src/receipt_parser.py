from __future__ import annotations

import base64
import json
from pathlib import Path

from openai import AsyncOpenAI

from src.models import ParsedReceipt

CATEGORY_VALUES = [
    "groceries",
    "restaurant",
    "cafe",
    "household",
    "personal_care",
    "health",
    "transport",
    "electronics",
    "clothing",
    "entertainment",
    "fees_taxes",
    "other",
]

SYSTEM_PROMPT = """You extract structured data from receipt images for a personal expense tracker.
Receipts may be in English, Thai, or mixed. Return only valid JSON. Do not use markdown.
Extract all visible details: merchant, address, date, receipt number, payment method, line items,
quantities, units, unit prices, totals, taxes, service charges, discounts, and issues.
Categorize each item with one category from the provided enum. If unsure, use other.
If item totals do not match receipt total, add an issue with needs_user_clarification=true; do not hide it.
Do not invent missing items. Use null for unknown optional fields.
"""


def _image_data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def receipt_json_schema(default_currency: str) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "merchant_name",
            "merchant_address",
            "receipt_date",
            "language",
            "currency",
            "items",
            "totals",
            "payment_method",
            "receipt_number",
            "issues",
            "overall_confidence",
        ],
        "properties": {
            "merchant_name": {"type": ["string", "null"]},
            "merchant_address": {"type": ["string", "null"]},
            "receipt_date": {"type": ["string", "null"], "description": "YYYY-MM-DD if visible"},
            "language": {"type": "string", "enum": ["en", "th", "mixed", "unknown"]},
            "currency": {"type": "string", "description": f"Use {default_currency} if no currency is visible."},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "original_name",
                        "category",
                        "quantity",
                        "unit",
                        "unit_price",
                        "total_price",
                        "currency",
                        "confidence",
                        "notes",
                    ],
                    "properties": {
                        "name": {"type": "string"},
                        "original_name": {"type": ["string", "null"]},
                        "category": {"type": "string", "enum": CATEGORY_VALUES},
                        "quantity": {"type": ["number", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "unit_price": {"type": ["number", "null"]},
                        "total_price": {"type": "number"},
                        "currency": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "notes": {"type": ["string", "null"]},
                    },
                },
            },
            "totals": {
                "type": "object",
                "additionalProperties": False,
                "required": ["subtotal", "tax", "service_charge", "discount", "total", "currency"],
                "properties": {
                    "subtotal": {"type": ["number", "null"]},
                    "tax": {"type": ["number", "null"]},
                    "service_charge": {"type": ["number", "null"]},
                    "discount": {"type": ["number", "null"]},
                    "total": {"type": ["number", "null"]},
                    "currency": {"type": ["string", "null"]},
                },
            },
            "payment_method": {"type": ["string", "null"]},
            "receipt_number": {"type": ["string", "null"]},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["severity", "message", "needs_user_clarification"],
                    "properties": {
                        "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                        "message": {"type": "string"},
                        "needs_user_clarification": {"type": "boolean"},
                    },
                },
            },
            "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


class ReceiptParser:
    def __init__(self, *, api_key: str, model: str, default_currency: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.default_currency = default_currency

    async def parse_image(self, image_path: Path) -> tuple[ParsedReceipt, str]:
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "receipt_parse",
                    "strict": True,
                    "schema": receipt_json_schema(self.default_currency),
                },
            },
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Parse this receipt. Default missing currency to "
                                f"{self.default_currency}. Use Thai item names in original_name "
                                "when visible and a concise English/normalized name in name if possible."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        parsed = ParsedReceipt.model_validate(json.loads(raw))
        return parsed, raw
