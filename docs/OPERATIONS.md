# Operations runbook

## Daily healthy run

A normal run:

1. applies migrations;
2. passes `doctor --strict`;
3. reports collected, clustered, candidate, and digest counts;
4. reports `sent: true` with a provider message ID;
5. pings the optional healthcheck.

The logs deliberately do not show headlines or the recipient.

## Manual commands

```bash
uv run finalboss doctor --strict
uv run finalboss doctor --strict --require-social
uv run finalboss migrate
uv run finalboss run --dry-run
uv run finalboss run
```

`run` sends. Use `--dry-run` during investigation.

## Common failures

| Symptom | Check | Safe action |
|---|---|---|
| `credentials_missing` on X/Reddit | Corresponding secrets/approval | Add valid approved credentials; never add a scraper |
| Fewer than five healthy sources | Source smoke workflow and publisher status | Wait/retry or disable confirmed-dead source |
| OpenRouter 401/402 | Dedicated key and credit cap | Rotate/fund key; deterministic fallback may still preview |
| OpenRouter 429/5xx | Provider status | Bounded retry occurs; fallback model/editorial remains |
| Invalid editorial output | Model compatibility | Pin a structured-output model; inspect contract test, not raw production prompt |
| Database schema unavailable | `FINALBOSS_DATABASE_URL`, Neon status, migration | Run `finalboss migrate`; do not bypass the ledger |
| Resend 403 | Test-domain recipient mismatch | Use account-owner recipient or verify a domain |
| Resend 409 | Changed payload under same key | Keep/retry stored pending body; do not invent a new daily key |
| `already_sent` | Existing daily ledger row | Expected; no action |
| GitHub schedule stopped | Repo inactive for 60 days | Re-enable workflow and manually dispatch |

## Source maintenance

The weekly Source smoke workflow performs a real public collection with no secrets and
no delivery. A single degraded source does not fail the run; fewer than five healthy
adapters does.

When a feed permanently moves:

1. verify the new publisher-provided HTTPS URL;
2. update `config/sources.yaml`;
3. retain the same source ID when it is the same publication;
4. add/update a sanitized parser fixture;
5. run tests and a local dry-run.

Do not follow a broken X/Reddit endpoint with an unofficial mirror.

## Duplicate-send recovery

The database unique key and Resend idempotency key are layered:

- before sending, a complete payload is saved as `pending`;
- a crash after provider acceptance retries the identical stored body/key;
- Resend deduplicates within 24 hours;
- the database remains authoritative after 24 hours.

Never delete a pending/failed row merely to force a send. Investigate provider status
and retry the job.

## Upgrade procedure

1. Review Dependabot PR and changelog.
2. Run `make check` and `make audit`.
3. Build the Docker image.
4. Validate migrations against a temporary database.
5. Run the daily workflow in `validate` mode.
6. Merge and observe the next scheduled run.
