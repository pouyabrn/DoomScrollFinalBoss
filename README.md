# DoomScroll Final Boss

Daily AI news from the useful parts of the internet, minus the part where you lose
three hours and somehow end up reading model benchmark discourse at 2am.

This is a private email briefing for you and up to nine people you trust, built in a
public repo without putting the private list in Git. It reads a curated set of official
feeds, research feeds, expert newsletters, OpenRouter, approved Reddit, and the
official X API. It clusters duplicate stories, ranks what actually matters, writes an
ELI5 explanation for each pick, sends at most 20, then ends with a cautious 2–3 line
read on what might happen in AI next week and one ready-to-post LinkedIn opportunity
for the next 24 hours.

The initial architecture and implementation pass was built with Codex SOL 5.6. The
repo is aggressively tested because “the model will probably return valid JSON” is how
you end up debugging email at breakfast 😭

## the honest version

X and Reddit cannot be scraped in a production project anymore. This repo does not
pretend otherwise.

- X uses official Recent Search, hard-capped at 10 posts per day. At the current
  $0.005 per post read, that is about $1.50/month.
- Reddit uses approved OAuth access with a descriptive user agent. Without approved
  credentials, it fails closed.
- Social posts are discovery and corroboration. Their raw bodies and authors are not
  stored, copied into email, or sent to the LLM.
- The actual reading list comes mostly from publisher-provided RSS/Atom, public sitemap
  metadata, OpenRouter’s official feeds, and linked primary sources.
- LinkedIn does not expose a normal API for searching arbitrary public posts. This app
  does not scrape it or fake a trend scan. The final email section turns the day's
  strongest verified news into a post draft and says exactly what its signal is based
  on.

“Every AI newsletter” here means an extensible, reviewed source registry, not random
internet scraping. The starter registry has 34 publisher/discovery sources plus two
social adapters across labs, research, infrastructure, expert newsletters, and press.
Add or remove them in
[`config/sources.yaml`](config/sources.yaml).

## what it does

```text
30 RSS/Atom feeds + 4 official sitemaps + OpenRouter catalog
                     + approved Reddit + paid official X
                                      |
                         normalize and cluster
                                      |
                    deterministic importance pre-rank
                                      |
                one strict top-20 LLM editorial pass
                                      |
                     final diverse top 20
                                      |
                  small strict LinkedIn writing pass
                                      |
                 ELI5 + forecast + post opportunity
                                      |
                  HTML and text email through Resend
                                      |
                 private Postgres idempotency ledger
```

The model never gets to make up a link. It returns existing item IDs and bounded prose;
the app owns titles, URLs, timestamps, attribution, ordering math, and send state.
The final section has an Impression Potential score and a separate Model Confidence
score. Both use transparent application math; confidence is capped at 65/100 until
first-party LinkedIn analytics are available, because a prediction without audience
history should look uncertain.

## expected monthly cost

For one email per day:

| Part | Expected cost |
|---|---:|
| GitHub Actions in a public repo | $0 |
| Neon Postgres free plan | $0 |
| Resend free plan | $0 |
| RSS, sitemaps, approved Reddit | $0 |
| OpenRouter `openai/gpt-oss-120b` at the expected batch size | about $0.11 |
| X, exactly 10 post reads/day | about $1.50 |
| Total before tax, FX, or provider changes | about $1.61 |

Set `llm.model: openrouter/free` for zero-cost LLM mode. It works for a personal
project, but free-model availability is not a production SLA. Set a $0.25 hard limit
on the dedicated OpenRouter key and roughly $1.50 on X.

The exact research and official links are in
[`docs/RESEARCH.md`](docs/RESEARCH.md).

## run it locally

You need Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/pouyabrn/DoomScrollFinalBoss
cd DoomScrollFinalBoss
uv sync --extra dev
cp .env.example .env
```

Fill in `.env`, then:

```bash
uv run finalboss migrate
uv run finalboss doctor
uv run finalboss run --dry-run
```

The dry run writes `preview/digest-YYYY-MM-DD.html` and does not send anything.

When `doctor --strict` is clean:

```bash
uv run finalboss run
```

That is a real send. The newsletter is generated once, then every configured person
gets a separate email. The database ledger and Resend idempotency key make reruns for
each recipient/date safe.

If you genuinely want another copy of the already-sent edition:

```bash
uv run finalboss run --force-resend
```

That command reuses today's exact stored HTML and text. It does not crawl again or
spend another LLM request. Each forced copy gets a database-backed resend sequence and
a distinct Resend idempotency key, so a crashed retry is still safe. The public default
allows at most three intentional resends per day.

## deploy the free setup

The default deployment is the checked-in GitHub Actions workflow. It runs every day at
08:17 in `Europe/Rome`, including daylight-saving changes.

Create a GitHub `production` environment and add these secrets:

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

The last four are optional to the generic project, but X and Reddit credentials are
needed for the full source mix requested by this instance. Use Actions → Daily digest →
Run workflow → `validate` first. Then run `send`. To send another copy of today's stored
edition, choose `force-resend` and tick the confirmation checkbox. Once everything
works, add a repository Actions variable named `FINALBOSS_ENABLED` with value `true`;
scheduled delivery stays disabled until that explicit switch exists.

### change the recipient list

Go to Settings → Environments → `production` → Environment secrets, then edit
`FINALBOSS_EMAIL_TO`. Put one address on each line, up to ten:

```text
you@example.com
friend@example.com
another-friend@example.com
```

Commas and semicolons also work, but one per line is harder to mess up. Duplicates and
case variants are collapsed. Every person gets a separate provider request, never a
visible CC/BCC list.

From an authenticated terminal, this command safely prompts for the multiline value
instead of putting it in the repository or command history:

```bash
gh secret set FINALBOSS_EMAIL_TO \
  --repo YOUR_GITHUB_NAME/DoomScrollFinalBoss \
  --env production
```

The `onboarding@resend.dev` test sender can send only to the address that owns the
Resend account. Before adding anyone else, verify a domain you own in Resend and change
`FINALBOSS_EMAIL_FROM` to something like `Final Boss <news@updates.yourdomain.com>`.
Recipients do not need to be added to Resend Contacts.

After changing the list, run the normal `send` action. Anyone already sent that day's
edition is skipped; newly added people get the exact stored edition without another
crawl or LLM bill. Removing an address stops future attempts for it.

### change the delivery time

Edit the schedule in [`.github/workflows/daily-digest.yml`](.github/workflows/daily-digest.yml):

```yaml
- cron: "17 8 * * *"
  timezone: "Europe/Rome"
```

The fields are `minute hour day-of-month month day-of-week`, so `"30 7 * * *"` means
07:30 every day in the named timezone. Commit the workflow change to the protected
default branch. The `timezone` line makes daylight-saving changes automatic.

### send from GitHub right now

Use Actions → Daily digest → Run workflow. Choose `send` for the first copy, or choose
`force-resend` plus the confirmation checkbox for another copy on the same day.

```bash
gh workflow run daily-digest.yml \
  --repo YOUR_GITHUB_NAME/DoomScrollFinalBoss \
  -f mode=force-resend \
  -F confirm_force=true
```

GitHub disables schedules in public repos after 60 days with no repository activity
and can delay cron during heavy load. A Render Cron blueprint is included as a roughly
$1/month reliability upgrade, but that would push the complete X setup beyond the
original budget. Full setup is in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## private email, public code

No recipient, sender, credential, private preference, rendered production email,
prompt, or provider response belongs in Git.

The workflow has read-only repository permissions, no secret-bearing PR job, pinned
Action SHAs, no production email artifacts, and no public newsletter archive. Resend
tracking stays off. The database stores a keyed fingerprint per recipient rather than
an address. Addresses exist only in the private environment secret and in memory while
that run sends.

“Private” still has a real-world boundary: GitHub runs the code, Neon stores the ledger,
OpenRouter processes the editorial batches, Resend transports the message, and your mail
provider receives it. Read [`docs/PRIVACY.md`](docs/PRIVACY.md) before putting sensitive
material into private source customizations.

## customize it

- General behavior: [`config/newsletter.yaml`](config/newsletter.yaml)
- Source registry: [`config/sources.yaml`](config/sources.yaml)
- Email HTML: [`src/finalboss/email/templates/digest.html.j2`](src/finalboss/email/templates/digest.html.j2)
- Plain text: [`src/finalboss/email/templates/digest.txt.j2`](src/finalboss/email/templates/digest.txt.j2)
- Ranking math: [`src/finalboss/processing/rank.py`](src/finalboss/processing/rank.py)
- Editorial contract: [`src/finalboss/llm/editor.py`](src/finalboss/llm/editor.py)
- LinkedIn scoring: [`src/finalboss/processing/linkedin.py`](src/finalboss/processing/linkedin.py)

The email uses a black-and-warm-white editorial control-panel system: huge index
numbers, tiny machine labels, hard rules, and one small signal color that changes
deterministically each day. It is a 640px table layout with inline CSS and a mobile
collapse, because an inbox is not a browser no matter how badly it wants to be one.
Before changing the markup, test it in Gmail, Outlook, and Apple Mail.

## quality bar

```bash
make check
make audit
```

Current local gate:

- 62 tests passing
- 84%+ branch-aware coverage
- Ruff clean
- strict mypy clean
- Bandit and `pip-audit` in CI
- CodeQL on pushes, pull requests, and weekly
- reproducible `uv.lock`
- migration-tested private send ledger

Start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) if you want the system design,
or [`CONTRIBUTING.md`](CONTRIBUTING.md) if you want to change it.
