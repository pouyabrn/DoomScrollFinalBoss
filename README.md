# DoomScroll Final Boss

Daily AI news from the useful parts of the internet, minus the part where you lose
three hours and somehow end up reading model benchmark discourse at 2am.

This is a private, one-person email briefing built in a public repo. It reads a curated
set of official feeds, research feeds, expert newsletters, OpenRouter, approved Reddit,
and the official X API. It clusters duplicate stories, ranks what actually matters,
writes an ELI5 explanation for each pick, sends at most 20, then ends with a cautious
2–3 line read on what might happen in AI next week.

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
                     one strict-schema LLM edit pass
                                      |
                diversity-aware top 20 + ELI5 + forecast
                                      |
                  HTML and text email through Resend
                                      |
                 private Postgres idempotency ledger
```

The model never gets to make up a link. It returns existing item IDs and bounded prose;
the app owns titles, URLs, timestamps, attribution, ordering math, and send state.

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

That is a real send. The database ledger and Resend idempotency key make reruns for the
same recipient/date safe.

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
Run workflow → `validate` first. Then run `send`. Once both work, add a repository
Actions variable named `FINALBOSS_ENABLED` with value `true`; scheduled delivery stays
disabled until that explicit switch exists.

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
tracking stays off. The database stores a keyed recipient fingerprint rather than the
address.

“Private” still has a real-world boundary: GitHub runs the code, Neon stores the ledger,
OpenRouter processes the editorial batch, Resend transports the message, and your mail
provider receives it. Read [`docs/PRIVACY.md`](docs/PRIVACY.md) before putting sensitive
material into private source customizations.

## customize it

- General behavior: [`config/newsletter.yaml`](config/newsletter.yaml)
- Source registry: [`config/sources.yaml`](config/sources.yaml)
- Email HTML: [`src/finalboss/email/templates/digest.html.j2`](src/finalboss/email/templates/digest.html.j2)
- Plain text: [`src/finalboss/email/templates/digest.txt.j2`](src/finalboss/email/templates/digest.txt.j2)
- Ranking math: [`src/finalboss/processing/rank.py`](src/finalboss/processing/rank.py)
- Editorial contract: [`src/finalboss/llm/editor.py`](src/finalboss/llm/editor.py)

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

- 38 tests passing
- 82%+ branch-aware coverage
- Ruff clean
- strict mypy clean
- Bandit and `pip-audit` in CI
- CodeQL on pushes, pull requests, and weekly
- reproducible `uv.lock`
- migration-tested private send ledger

Start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) if you want the system design,
or [`CONTRIBUTING.md`](CONTRIBUTING.md) if you want to change it.
