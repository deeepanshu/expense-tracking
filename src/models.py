from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExpenseCategory(StrEnum):
    GROCERIES = "groceries"
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    HOUSEHOLD = "household"
    PERSONAL_CARE = "personal_care"
    HEALTH = "health"
    TRANSPORT = "transport"
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    ENTERTAINMENT = "entertainment"
    FEES_TAXES = "fees_taxes"
    OTHER = "other"


class ParseIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["info", "warning", "error"]
    message: str
    needs_user_clarification: bool = False


class ReceiptItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    original_name: str | None = None
    category: ExpenseCategory = ExpenseCategory.OTHER
    quantity: Annotated[float, Field(gt=0)] | None = None
    unit: str | None = None
    unit_price: Annotated[float, Field(ge=0)] | None = None
    total_price: Annotated[float, Field(ge=0)]
    currency: str | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] = 0.0
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper().strip() if value else None

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None


class ReceiptTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtotal: Annotated[float, Field(ge=0)] | None = None
    tax: Annotated[float, Field(ge=0)] | None = None
    service_charge: Annotated[float, Field(ge=0)] | None = None
    discount: Annotated[float, Field(ge=0)] | None = None
    total: Annotated[float, Field(ge=0)] | None = None
    currency: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper().strip() if value else None


class ParsedReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_name: str | None = None
    merchant_address: str | None = None
    receipt_date: date | None = None
    language: Literal["en", "th", "mixed", "unknown"] = "unknown"
    currency: str
    items: list[ReceiptItem] = Field(default_factory=list)
    totals: ReceiptTotals = Field(default_factory=ReceiptTotals)
    payment_method: str | None = None
    receipt_number: str | None = None
    issues: list[ParseIssue] = Field(default_factory=list)
    overall_confidence: Annotated[float, Field(ge=0, le=1)] = 0.0

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper().strip()

    @model_validator(mode="after")
    def fill_item_currencies_and_detect_total_mismatch(self) -> ParsedReceipt:
        for item in self.items:
            if item.currency is None:
                item.currency = self.currency
        if self.totals.currency is None:
            self.totals.currency = self.currency

        item_sum = round(sum(item.total_price for item in self.items), 2)
        if self.totals.total is not None:
            expected = round(self.totals.total, 2)
            # Discounts, taxes, and service charges may explain a mismatch. Flag, do not reject.
            components = (self.totals.tax or 0) + (self.totals.service_charge or 0) - (self.totals.discount or 0)
            adjusted = round(item_sum + components, 2)
            if abs(adjusted - expected) > 0.05:
                self.issues.append(
                    ParseIssue(
                        severity="warning",
                        message=(
                            f"Item total {item_sum:.2f} plus adjustments {components:.2f} "
                            f"does not match receipt total {expected:.2f}."
                        ),
                        needs_user_clarification=True,
                    )
                )
        return self


class StoredReceiptVersion(BaseModel):
    id: int
    receipt_id: int
    version_number: int
    source: Literal["ai", "user_correction"]
    status: Literal["pending", "approved", "rejected"]
    parsed: ParsedReceipt
