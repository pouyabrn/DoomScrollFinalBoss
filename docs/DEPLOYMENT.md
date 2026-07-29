# Deployment

## Recommended setup

Use GitHub Actions for the scheduler/runtime, Neon for private state, OpenRouter for
one editorial batch, and Resend for delivery.

No deployment can be completed safely until accounts, approvals, recipient/sender, and
secrets exist. The repository contains the deployable workflow; the personal
credentials stay outside Git.

## 1. Neon

1. Create a free Neon project near the runtime region.
2. Copy its pooled Postgres URL with `sslmode=require`.
3. Save it as `FINALBOSS_DATABASE_URL`.
4. Do not paste it into an issue, commit, workflow YAML, or log.

The daily workflow runs `finalboss migrate` before doing any work.

## 2. Resend

For a self-newsletter, the fastest free start is:

1. Create a Resend account.
2. Create a sending-only API key.
3. Use `Final Boss <onboarding@resend.dev>` as `FINALBOSS_EMAIL_FROM`.
4. Set `FINALBOSS_EMAIL_TO` to the email that owns the Resend account.
5. Keep open/click tracking disabled.

For another recipient or a real sender address, verify a domain with SPF/DKIM and add
DMARC before changing the sender.

## 3. OpenRouter

1. Create a dedicated API key, not a general personal key.
2. Set a hard credit limit around $0.25/month.
3. Store it as `FINALBOSS_OPENROUTER_API_KEY`.
4. Keep `openai/gpt-oss-120b` or choose another structured-output model.
5. Use `openrouter/free` only when variable availability is acceptable.

Set `require_zero_data_retention: true` in `config/newsletter.yaml` only after verifying
that every configured model/provider supports it.

## 4. X

1. Apply for an X developer project with the truthful personal news-analysis use case.
2. Enable pay-per-use and set a provider-side spending cap around $1.50/month.
3. Create a read credential and store its bearer token as
   `FINALBOSS_X_BEARER_TOKEN`.
4. Keep `x_max_posts_per_day: 10`.

The adapter issues one Recent Search request and asks for exactly 10 results. Do not
replace it with scraping if access is unavailable.

## 5. Reddit

1. Request/confirm approved Reddit Data API access for the personal use case.
2. Create an OAuth client permitted for this job.
3. Store its ID and secret as `FINALBOSS_REDDIT_CLIENT_ID` and
   `FINALBOSS_REDDIT_CLIENT_SECRET`.
4. Keep the descriptive public project User-Agent in `config/newsletter.yaml`.

The adapter reads link submissions only and ignores self-posts/comments.

## 6. Privacy and monitoring keys

Generate a keyed-hash secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Store it as `FINALBOSS_PRIVACY_KEY`. It must remain stable; changing it changes the
recipient ledger identity.

Optionally create a free Healthchecks-style check and store its ping URL as
`FINALBOSS_HEALTHCHECK_URL`. It is a secret because the URL path contains a token.

## 7. GitHub environment

Create an environment named `production`, restrict deployment branches to `main`, and
add:

```text
FINALBOSS_DATABASE_URL
FINALBOSS_OPENROUTER_API_KEY
FINALBOSS_RESEND_API_KEY
FINALBOSS_EMAIL_TO
FINALBOSS_EMAIL_FROM
FINALBOSS_PRIVACY_KEY
FINALBOSS_X_BEARER_TOKEN
FINALBOSS_REDDIT_CLIENT_ID
FINALBOSS_REDDIT_CLIENT_SECRET
FINALBOSS_HEALTHCHECK_URL
```

The first six are required for delivery. Social and healthcheck values are optional to
the generic repo, but X/Reddit are needed for the complete configured source mix.

Enable:

- Actions;
- secret scanning and push protection;
- private vulnerability reporting;
- Dependabot security updates;
- branch protection requiring CI and CodeQL.

## 8. First deployment

1. Push the repository to `main`.
2. Open Actions → Daily digest → Run workflow.
3. Choose `validate`.
4. Inspect safe count/status output. The generated email is deliberately not uploaded.
5. Run the same workflow with `send`.
6. Confirm the message in Resend and the recipient inbox.
7. Run `send` again; it should report `already_sent` without another provider call.
8. Add a repository Actions variable `FINALBOSS_ENABLED=true`.

For an intentional second copy on the same day, choose `force-resend` and tick
`confirm_force`. This sends the already stored edition with a separate audited
idempotency key; it does not run collection or OpenRouter again.

## Change the recipient

Update the `FINALBOSS_EMAIL_TO` environment secret under Settings → Environments →
`production`. Do not put an address in workflow YAML, repository variables, an issue,
or a command argument that will remain in shell history.

The current private mode supports one recipient per deployment. Use a separate
deployment for another recipient so delivery ledgers and addresses stay isolated.
Resend's test domain can deliver only to the Resend account owner's address; verify a
domain before sending to anyone else.

## Change the schedule

The cron runs at 08:17 in `Europe/Rome`:

```yaml
- cron: "17 8 * * *"
  timezone: "Europe/Rome"
```

Cron fields are minute, hour, day of month, month, and day of week. For example,
`"30 7 * * *"` is 07:30 daily in the configured timezone. Change the workflow through
the normal protected-branch review path; do not add a second scheduler for the same
deployment.

Avoid minute `0`, when GitHub schedule load is highest.
The scheduled job remains safely skipped while `FINALBOSS_ENABLED` is absent or false;
manual validation and send remain available.

## Render reliability upgrade

`render.yaml` defines a Frankfurt cron job. Render schedules are UTC, so its checked-in
07:17 schedule corresponds to 08:17 Rome only during standard time. Adjust it during
DST or choose a fixed UTC preference.

Render Cron has roughly a $1/month minimum and pushes the full X configuration past
the requested ceiling. Use it only when scheduler reliability matters more than the
strict budget.

## Docker

Build and validate:

```bash
docker build -t doomscroll-final-boss .
docker run --env-file .env doomscroll-final-boss doctor --strict
```

Run migration and delivery as separate commands:

```bash
docker run --env-file .env doomscroll-final-boss migrate
docker run --env-file .env doomscroll-final-boss run
```

Never bake `.env` into the image.
