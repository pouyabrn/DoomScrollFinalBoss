# DoomScrollFinalBoss contributor guide

## Product contract

- This repository is public, but every personal value and credential is private.
- Never commit recipient addresses, API keys, database URLs, private preferences, rendered production emails, or raw API responses.
- Ingestion is RSS/API-first. Do not add scraping for X or Reddit.
- The LLM is an editor, not a crawler. It may select IDs and write grounded summaries, but it must never supply links or invoke tools from source content.
- A digest contains at most 20 credible, deduplicated stories. Never invent filler.
- Every send must be protected by both the database ledger and the email provider's idempotency key.

## Engineering rules

- Target Python 3.12 and keep `mypy --strict`, Ruff, and pytest green.
- Use bounded concurrency, explicit timeouts, response-size limits, and isolated source failures.
- Treat all feed/API text as untrusted. Escape it in HTML and delimit it in prompts.
- Preserve the deterministic fallback path; a model outage must not corrupt state or fabricate content.
- Log public identifiers and counts only. Never log prompts, excerpts, recipients, HTML, auth headers, or full provider responses.
- Add or update tests with every behavior change.

## Repository map

- `src/finalboss/sources/`: external ingestion boundary; see its local `AGENTS.md`.
- `src/finalboss/llm/`: OpenRouter and structured-output boundary; see its local `AGENTS.md`.
- `src/finalboss/email/`: rendering and delivery boundary; see its local `AGENTS.md`.
- `tests/`: fixture-only CI tests; see its local `AGENTS.md`.
- `config/`: public, non-secret defaults and source registry.
- `docs/`: architecture, operations, privacy, and deployment decisions.

## Safe verification

```bash
python -m pytest
ruff check .
ruff format --check .
mypy src
python -m finalboss doctor
python -m finalboss run --dry-run --fixture tests/fixtures/stories.json
```
