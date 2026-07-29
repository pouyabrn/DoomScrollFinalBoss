# Storage boundary

- The database is authoritative for daily uniqueness. Never send when it is unavailable.
- Store a recipient HMAC only; never persist the address or any provider credential.
- Persist the exact pending HTML/text payload before calling the email provider so crash recovery can reuse the same idempotency key and bytes.
- Migrations must be reviewed, reversible when practical, and tested on SQLite plus production-compatible Postgres semantics.
- Never delete a pending/failed digest to force a resend. Reconcile and retry it.
- Database/log errors are reduced to safe exception categories before leaving this boundary.
