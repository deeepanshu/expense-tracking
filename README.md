# Expense Tracker MVP

Personal Discord receipt tracker. Upload a receipt image in one dedicated Discord channel; the bot stores the image locally, asks OpenAI vision to parse English/Thai receipt details, shows an itemized summary, and saves to SQLite only after you press **Approve**.

## MVP choices

- Language/runtime: Python 3.12 managed by `uv`
- Discord: dedicated channel only
- AI: OpenAI vision model (`gpt-4o-mini` by default)
- Storage: SQLite + local receipt images, managed through SQLAlchemy ORM
- Confirmation: Discord Approve / Reject buttons
- Default currency: THB when missing
- Categories: groceries, restaurant, cafe, household, personal care, health, transport, electronics, clothing, entertainment, fees/taxes, other

## Corrections/versioning model

Every receipt has many `receipt_versions`:

- version 1: raw AI parse, with raw model output stored
- future versions: user corrections, also stored as full normalized JSON
- only one version is approved and materialized into the `items` table

The MVP supports approve/reject. The schema/database are already designed so a later correction UI can create version 2, 3, etc. without losing the original AI output.

## Setup

```bash
uv sync --extra dev
cp .env.example .env
```

Secrets can live in `/home/deepanshu/config/shared.secrets.env`:

```env
DISCORD_BOT_TOKEN=...
OPENAI_API_KEY=...
```

Then keep project-specific values in `.env`:

```env
RECEIPT_CHANNEL_ID=...
OPENAI_RECEIPT_MODEL=gpt-4o-mini
OPENAI_CORRECTION_MODEL=gpt-4o-mini
DEFAULT_CURRENCY=THB
```

`DISCORD_TOKEN` and `OPENAI_MODEL` are also accepted as backwards-compatible aliases.

Discord bot requirements:

- Add the bot to your server.
- Enable Message Content Intent in the Discord Developer Portal.
- Give it permission to read/send messages in the receipt channel.
- Enable Discord developer mode, right-click the channel, and copy its ID into `RECEIPT_CHANNEL_ID`.

## Run locally

```bash
uv run python -m src.bot
```

## Docker Compose

The service joins both the project default network and the external `observability` network. It emits structured JSON logs to stdout and exports OpenTelemetry traces/metrics to `http://otel-collector:4318` by default.

Create the external network once if it does not exist:

```bash
docker network create observability
```

Then run:

```bash
make up
make logs
make down
```

Current metrics/traces include receipt images received, parse success/failure, approval/rejection counts, image size, and AI parse duration. Override with `OTEL_EXPORTER_OTLP_ENDPOINT` or disable with `OTEL_ENABLED=false`.

## Checks

```bash
make check
```

## Export approved items

```bash
make export-csv
```

This writes `expenses.csv` from approved receipt items.
