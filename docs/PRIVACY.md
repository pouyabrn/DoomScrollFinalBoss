# Privacy model

## What “private” means here

The repository can be public without exposing:

- recipient or sender address;
- provider/API credentials;
- private database URL;
- private preferences or authenticated feed URLs;
- rendered production email;
- raw model/provider/social responses;
- healthcheck token.

There is no public archive, tracking pixel, click rewriting, or production-email
artifact.

It does not mean that infrastructure providers cannot process the message. GitHub runs
the job, Neon stores its ledger, OpenRouter and its selected provider process the
editorial batch, Resend transports/temporarily retains email content, and the mailbox
provider receives it. End-to-end secrecy would require PGP/S/MIME and would materially
change the HTML-email experience.

## Data minimization

The application persists:

- one keyed fingerprint per recipient, not any address;
- rendered pending/sent digest for crash-safe idempotency;
- public story fingerprint, URL, source ID, and position;
- provider message ID;
- safe counts, timestamps, statuses, and redacted error categories.

It does not persist raw feed bodies, X/Reddit post bodies, social authors, comments,
prompts, or full provider responses.

The configured list supports up to ten addresses. It exists only in the private
runtime secret and memory during delivery. The sender makes one provider request per
address; it never exposes the list through `To`, CC, or BCC.

The email body is retained in the private database because exactly-once crash recovery
requires retrying the exact payload. Set a database retention/deletion policy that
matches your needs.

## Social platform policy

- Reddit: OAuth only; link submissions only; no self-post/comment content; no user data
  persisted.
- X: official Recent Search only; external article links and aggregate metrics are
  ephemeral corroboration; no post body persisted.
- LinkedIn: no collection or scraping. The topic opportunity is generated from the
  day's verified publisher stories. No profile, connection, audience, or post-analytics
  data is requested or stored.

Deleting a social record is therefore normally satisfied when the daily process exits.

## Model boundary

The model sees public titles, short feed excerpts, public source metadata, and aggregate
metrics. It does not see the recipient, sender, database URL, credentials, or private
delivery state.

OpenRouter/provider privacy policies vary. Zero-data-retention routing is configurable
but off by default because it can reduce compatible model availability. Review the
selected model/provider before enabling private source customizations.

## Logs

Logs contain event names, safe source IDs, counts, durations, run IDs, and exception
class names. The app suppresses HTTP request logs because a healthcheck URL can contain
a token. It never intentionally logs message bodies, prompts, recipient, sender,
headers, or complete provider errors.

Anyone with write access to a repository can alter a workflow to expose repository
secrets. Keep write access narrow and protect the production environment/default
branch with required reviews.
