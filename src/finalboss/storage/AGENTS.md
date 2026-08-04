# Storage boundary

- The database is authoritative for daily uniqueness. Never send when it is unavailable.
- Store one recipient HMAC per delivery only; never persist an address or provider credential.
- Persist the exact pending HTML/text payload before calling the email provider so crash recovery can reuse the same idempotency key and bytes.
- Reserve every intentional resend in its own append-only sequence before provider contact.
  In a recipient batch, retry only unfinished sequences; never allocate a new sequence
  for successful peers while any configured recipient remains unfinished.
- Migrations must be reviewed, reversible when practical, and tested on SQLite plus production-compatible Postgres semantics.
- Never delete a pending/failed digest to force a resend. Reconcile and retry it.
- Database/log errors are reduced to safe exception categories before leaving this boundary.
