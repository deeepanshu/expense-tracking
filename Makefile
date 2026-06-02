.PHONY: check lint type test up down restart logs ps export-csv sync

sync:
	uv sync --extra dev

lint:
	uv run ruff check src tests

type:
	uv run mypy src tests

test:
	uv run pytest

check: lint type test

up:
	docker compose up -d --build --force-recreate

down:
	docker compose down

restart:
	docker compose up -d --build --force-recreate

logs:
	docker compose logs -f

ps:
	docker compose ps

export-csv:
	uv run python -m src.export_csv > expenses.csv
