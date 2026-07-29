# Contributing

Thanks for helping make the briefing less noisy.

1. Fork the repository and create a focused branch.
2. Install with `uv sync --extra dev`.
3. Read the root `AGENTS.md` and the nearest scoped `AGENTS.md`.
4. Add tests for behavior changes.
5. Run `make check` and `make audit`.
6. Open a pull request that explains the user impact, risk, and verification.

Source additions need a publisher-provided RSS/Atom feed or documented official API,
a clear terms note, bounded item count, and a sanitized fixture. X/Reddit scraping
workarounds will not be accepted.

Never include real secrets, addresses, private preference data, raw social responses,
or rendered production mail in a pull request.
