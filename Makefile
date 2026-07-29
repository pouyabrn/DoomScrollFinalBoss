.PHONY: audit check format install migrate preview test

install:
	uv sync --extra dev

format:
	uv run ruff format .
	uv run ruff check . --fix

test:
	uv run pytest

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy src
	uv run pytest
	uv run bandit -c pyproject.toml -r src

audit:
	uv run pip-audit

migrate:
	uv run finalboss migrate

preview:
	uv run finalboss run --dry-run
