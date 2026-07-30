# Research notes

Research date: 29 July 2026.

This document records the current platform facts behind the implementation. Provider
pricing and policies change; re-check the linked primary sources before raising caps.

Implementation API usage was checked through Context7 against the current Feedparser,
Pydantic Settings, Jinja, HTTPX, Tenacity, and related library documentation. Platform
policy and pricing decisions still use the first-party links below rather than a
library-documentation index.

## Source access

### X

X says developers must use its official API rather than scraping or browser automation.
Recent Search covers seven days and supports 10–100 results/request. Pay-per-use
pricing is currently $0.005 per post read, so a hard cap of 10 posts/day is about
$1.50/month.

- [X API pricing](https://docs.x.com/x-api/getting-started/pricing)
- [Recent Search](https://docs.x.com/x-api/posts/search/introduction)
- [X API rate limits](https://docs.x.com/x-api/fundamentals/rate-limits)
- [Developer guidelines](https://docs.x.com/developer-guidelines)
- [Developer agreement](https://docs.x.com/developer-terms/agreement)

Decision: one official query/day, 10 results, external links used as corroboration.
No scraping and no raw post persistence.

### Reddit

Reddit now requires registered OAuth access, blocks unauthenticated API traffic, and
requires a descriptive User-Agent. Its current terms restrict derivative use and
require handling deletions; Reddit recommends routinely purging stored user data.

- [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- [Data API Terms](https://redditinc.com/policies/data-api-terms)
- [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
- [Official API reference](https://www.reddit.com/dev/api/)

Decision: approved OAuth only, external link submissions only, ephemeral aggregate
engagement, no self-post bodies/comments/authors in model, mail, logs, or database.

### OpenRouter discovery

OpenRouter exposes an official blog feed and Models API RSS representation:

- `https://openrouter.ai/blog/feed.xml`
- `https://openrouter.ai/api/v1/models?use_rss=true`

The Models API is documented as edge-cached and can sort newest models.

- [Models API and RSS](https://openrouter.ai/docs/guides/overview/models)
- [OpenRouter blog](https://openrouter.ai/blog/all/)

### Publisher/newsletter sources

Thirty RSS/Atom URLs in `config/sources.yaml` were live-tested successfully on the
research date. Anthropic, Mistral, Cohere, and Stability AI did not offer a reliable
feed, so the adapter reads only their official public sitemap URL and `lastmod`
metadata. It does not fetch page bodies.

Meta AI is intentionally not scraped; its robots policy prohibits automated
collection without permission.

### LinkedIn post discovery and analytics

LinkedIn's self-serve Share on LinkedIn product supports publishing for an
authenticated member with `w_member_social`; it does not provide arbitrary public-post
search. Community Management access is a vetted product aimed primarily at managed
organization/member activity. LinkedIn's current access documentation says
`r_member_social` is closed and new access requests are not being accepted.
First-party post analytics permissions exist through approved Community Management
access, but they do not turn the API into a general public trend scanner.

- [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin)
- [Community Management API overview](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview?view=li-lms-2026-03)
- [Increasing access and closed member-read permission](https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access?view=li-lms-2026-05)
- [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-04)
- [Community Management app review](https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review?view=li-lms-2026-01)

Decision: no LinkedIn scraping and no claim of a public-post scan. The daily email
derives one post opportunity from its already verified news set, grounds it in final
item IDs, computes conservative scores in application code, and discloses the signal
basis. Approved first-party analytics can be added later as private calibration input.

## LLM/editorial

OpenRouter supports strict JSON Schema through `response_format`. Its guidance says to
set strict mode and `provider.require_parameters=true`. Free models are capped and
variable; OpenRouter itself says they are generally not a production guarantee.

- [Structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Free router](https://openrouter.ai/docs/guides/routing/routers/free-router)
- [FAQ and free-model limits](https://openrouter.ai/docs/faq)
- [Error and Retry-After behavior](https://openrouter.ai/docs/api/reference/errors-and-debugging)
- [Zero-data-retention routing](https://openrouter.ai/docs/guides/features/zdr)

The live pricing snapshot for `openai/gpt-oss-120b` was $0.037/M input and $0.17/M
output. An estimated 63k input and 8.5k output tokens/day across the main editorial
batch and a small final-story LinkedIn pass remains about $0.11/month. Both calls use
strict schemas and deterministic outage fallbacks. The deployment owner should enforce
a $0.25 key limit.

## Email

Resend’s free transactional tier currently includes 3,000 emails/month and 100/day. It
supports HTML and text bodies plus idempotency keys retained for 24 hours. The
`resend.dev` test sender may send only to the Resend account owner; other recipients
need a verified domain.

- [Resend pricing](https://resend.com/docs/knowledge-base/what-is-resend-pricing)
- [Send API](https://resend.com/docs/api-reference/emails/send-email)
- [Idempotency keys](https://resend.com/docs/dashboard/emails/idempotency-keys)
- [Test-domain restriction](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain)
- [Domain verification](https://resend.com/docs/dashboard/domains/introduction)
- [Tracking](https://resend.com/docs/dashboard/domains/tracking)

Alternatives considered:

| Provider | Finding |
|---|---|
| Buttondown | Good privacy posture, but subscriber/archive machinery is unnecessary for one person |
| Brevo | Large free quota, but free branding weakens the custom email |
| Postmark | 100 free emails/month; enough but little test/retry headroom |
| Amazon SES | Extremely cheap, but more AWS/IAM and sandbox setup than this needs |

## Scheduling and storage

GitHub Actions standard hosted runners are free for public repositories. Schedules can
use an IANA timezone, may be delayed under load, run only on the default branch, and
are disabled after 60 days without public-repo activity.

- [Actions billing](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [Schedule behavior and timezones](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Actions secrets](https://docs.github.com/en/actions/concepts/security/secrets)
- [Secure use](https://docs.github.com/en/actions/reference/security/secure-use)

Neon’s free Postgres plan currently includes 0.5 GB storage and 100 CU-hours/month per
project, with scale-to-zero. That is far beyond this ledger’s requirements.

- [Neon pricing](https://neon.com/pricing)
- [Python connection guide](https://neon.com/docs/guides/python)

Hosting alternatives:

| Platform | Current fit |
|---|---|
| GitHub Actions | Best $0 default; inactivity and cron-delay caveats |
| Render Cron | Better scheduler reliability, about $1/month minimum |
| Vercel Hobby Cron | Free daily, but no retries and loose execution window |
| Cloudflare Workers Free | 10ms CPU and 50 subrequests are too tight for 34 sources |

- [Render Cron Jobs](https://render.com/docs/cronjobs)
- [Vercel Cron limits](https://vercel.com/docs/cron-jobs/usage-and-pricing)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)

## Cost conclusion

The full direct-X version is approximately:

```text
GitHub + Neon + Resend + approved Reddit     $0.00
OpenRouter editorial batch                   $0.11
X: 10 post reads/day                         $1.50
Expected total                               $1.61/month
```

Tax, currency conversion, purchase fees, or future pricing can break the €2 ceiling.
Provider-side hard caps are required. Removing X makes the project effectively free.
