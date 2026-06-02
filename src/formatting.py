from __future__ import annotations

from src.models import ParsedReceipt


def money(value: float | None, currency: str) -> str:
    if value is None:
        return "?"
    return f"{value:,.2f} {currency}"


def format_receipt_summary(parsed: ParsedReceipt, *, receipt_id: int, version_id: int) -> str:
    lines = [
        f"🧾 Receipt #{receipt_id} · Version {version_id}",
        f"Merchant: {parsed.merchant_name or 'Unknown'}",
        f"Date: {parsed.receipt_date.isoformat() if parsed.receipt_date else 'Unknown'}",
        f"Language: {parsed.language} · Confidence: {parsed.overall_confidence:.0%}",
        "",
        "Items:",
    ]

    if not parsed.items:
        lines.append("- No line items found")
    else:
        for idx, item in enumerate(parsed.items[:20], start=1):
            qty = f" × {item.quantity:g}{item.unit or ''}" if item.quantity is not None else ""
            unit_price = f" @ {money(item.unit_price, item.currency or parsed.currency)}" if item.unit_price is not None else ""
            lines.append(
                f"{idx}. {item.name}{qty}{unit_price} — "
                f"{money(item.total_price, item.currency or parsed.currency)} [{item.category.value}]"
            )
        if len(parsed.items) > 20:
            lines.append(f"...and {len(parsed.items) - 20} more items")

    lines.extend(
        [
            "",
            f"Subtotal: {money(parsed.totals.subtotal, parsed.currency)}",
            f"Tax: {money(parsed.totals.tax, parsed.currency)}",
            f"Service: {money(parsed.totals.service_charge, parsed.currency)}",
            f"Discount: {money(parsed.totals.discount, parsed.currency)}",
            f"Total: {money(parsed.totals.total, parsed.currency)}",
        ]
    )

    clarification_issues = [issue for issue in parsed.issues if issue.needs_user_clarification]
    if parsed.issues:
        lines.append("")
        lines.append("Issues / clarification needed:" if clarification_issues else "Issues:")
        for issue in parsed.issues[:5]:
            lines.append(f"- {issue.severity}: {issue.message}")

    lines.append("")
    lines.append("Approve to save this version, or reject and upload/try again. Correction editing comes next.")
    return "\n".join(lines)
