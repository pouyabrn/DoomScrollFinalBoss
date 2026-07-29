# Test rules

- Pull-request tests never call live networks or consume production secrets.
- Use sanitized RSS/API fixtures and `respx` for adapter/provider contracts.
- Assert behavior, privacy, idempotency, grounding, and failure policy—not internal implementation trivia.
- Every external adapter needs success and failure coverage.
- Generated/model text must be tested as hostile HTML and prompt-injection input.
- Property tests should cover URL normalization, score bounds, stable ordering, and escaping.
- End-to-end tests use SQLite, fake source data, fake model output or deterministic fallback, and a mocked sender.
- Never commit real provider responses, usernames, email addresses, API keys, or production newsletter HTML.
