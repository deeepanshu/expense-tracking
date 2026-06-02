# Expense Tracker MVP Plan

## Confirmed MVP Scope

- Runtime: Python 3.12 with `uv` for version/dependency management.
- Discord flow: bot watches one dedicated receipt channel.
- Access: anyone who can post in that channel can submit receipts.
- AI provider: OpenAI vision.
- Languages: English, Thai, or mixed receipts.
- Storage: SQLite database plus local original receipt images.
- Default currency: THB when missing; preserve detected currency otherwise.
- Confirmation: always show parsed result with Approve / Reject buttons before saving.
- Raw AI output: store it for every AI parse.
- Corrections: model as new immutable receipt versions. MVP has approve/reject; later correction UI will create version 2+ rather than overwriting version 1.
- Categories: basic item categories included in normalized schema.
- Receipt details: parse merchant, address, date, payment method, receipt number, items, quantities, units, prices, subtotal, tax, service charge, discount, total, issues, confidence.
- Total mismatch: do not reject automatically; flag as a clarification issue.
- Export: CSV export for approved items included.

## Implemented Files

- `pyproject.toml` - Python project, dependencies, ruff/mypy/pytest config.
- `.python-version` - Python 3.12 for uv.
- `src/models.py` - Pydantic normalized receipt schema with categories and mismatch detection.
- `src/settings.py` - typed environment settings.
- `src/receipt_parser.py` - OpenAI vision parser with strict JSON schema.
- `src/db.py` - SQLite schema, receipt/version/item persistence, approve/reject, CSV rows.
- `src/formatting.py` - Discord receipt summary formatting.
- `src/bot.py` - Discord bot for dedicated channel ingestion and approval buttons.
- `src/export_csv.py` - CSV export entrypoint.
- `.env.example` - configuration template.
- `Dockerfile`, `docker-compose.yml`, `Makefile` - local/container workflows.
- `README.md` - setup and operating docs.
- `tests/` - model and formatting tests.

## Next Improvements After MVP

1. Add Discord correction UI that creates new `receipt_versions` from edited fields.
2. Add monthly/category summaries in Discord.
3. Add richer CSV/JSON export options with date filters.
4. Add OCR fallback if OpenAI struggles with a receipt.
5. Add owner/admin controls if the channel later includes more people.
