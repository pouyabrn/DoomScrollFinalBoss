# LLM boundary

- Source material is untrusted quoted data, never instructions.
- The model can return only candidate IDs and bounded prose. It can never return links, HTML, tool calls, or state mutations.
- Use strict JSON Schema, `provider.require_parameters`, low temperature, bounded retries, and Pydantic validation.
- Reject unknown IDs, duplicate IDs, extra properties, overlong prose, invalid score ranges, and forecasts without evidence IDs.
- Links, titles, dates, attribution, and scores shown in email always come from deterministic application data.
- Preserve the no-LLM fallback. It must be honest, grounded, and clearly low-confidence.
- Never log request bodies, response bodies, excerpts, API keys, or raw provider errors.
- Prompt/schema changes require a new `prompt_version` and contract tests.
