# Architecture

## Decision

DoomScroll Final Boss is a Python 3.12 modular monolith executed as a bounded daily
batch job. Crawling is deterministic. The LLM is used only for semantic editorial
judgment, ELI5 prose, a short grounded forecast, and one news-grounded LinkedIn draft.

This avoids an autonomous-agent crawler: it is more predictable, cheaper, easier to
audit, and much safer around prompt injection and platform terms.

## Data flow

```text
Publisher RSS/Atom ─┐
Official sitemaps ──┤
OpenRouter feeds ───┤
Reddit OAuth ───────┼──> normalized Story records
X Recent Search ────┘          |
                               v
                   exact URL + fuzzy title clusters
                               |
                               v
                    deterministic importance score
                               |
                               v
                       at most 50 candidates
                               |
                               v
                   OpenRouter strict JSON Schema
                               |
                               v
                 deterministic validation and blend
                               |
                               v
               at most 20 diverse, credible DigestItems
                               |
                 small grounded LinkedIn model call
                               |
                               v
                validated draft + bounded app scores
                               |
                  ┌────────────┴────────────┐
                  v                         v
             Jinja + CSS inline        plain text render
                  └────────────┬────────────┘
                               v
                Postgres pending outbox rows per recipient
                               |
                               v
              one idempotent Resend request per recipient
                               |
                               v
                      ledger marked as sent
```

## Trust boundaries

Source titles, descriptions, sitemap values, social metadata, and LLM prose are
untrusted. The pipeline:

1. permits only public HTTPS URLs;
2. rejects localhost, private/reserved literal IPs, excessive redirects, and oversized
   responses;
3. strips markup from feed and model prose;
4. sends the model compact quoted records without tools;
5. accepts only strict-schema item IDs and bounded text;
6. rejects unknown/duplicate IDs and ungrounded forecast or LinkedIn evidence;
7. takes every output link from validated application state.

## Source adapters

Each adapter implements:

```python
class SourceAdapter(Protocol):
    async def collect(self, *, since: datetime) -> CollectionResult: ...
```

- RSS/Atom: publisher-provided feeds parsed from bounded response bytes.
- Sitemap: public URL and `lastmod` metadata only; no generic body scraping.
- Reddit: approved OAuth, external link submissions only, no self-posts/comments.
- X: official Recent Search, one query and at most 10 results/day.

Social-only records are dropped unless their external URL corroborates a publisher
story. Social text/authors are never persisted or sent to the model/email provider.

## Ranking

The deterministic pre-score is explainable and capped:

- source authority and source-specific weight;
- exponential freshness decay;
- independent corroboration;
- log-capped social engagement;
- high-impact topic terms;
- penalties for clickbait and missing evidence.

The model assigns a 0–100 importance score while writing grounded editorial copy. Final
score:

```text
58% LLM importance + 42% deterministic importance
```

Selection first applies source/category diversity caps, then treats them as soft caps
when necessary to preserve the user-requested top 20. It never fabricates or pads
beyond the credible model-returned set.

## LinkedIn opportunity

The final email section is not a LinkedIn crawler. Standard official access does not
permit searching arbitrary public member posts, and closed member-read permissions
cannot be used by this project. After the top 20 is final, a separate small model call
chooses a topic and writes a bounded draft using up to eight final digest item IDs.
Keeping this contract separate prevents post-writing failure from discarding the
proven news edit. The application replaces the whole draft with deterministic
source-text prose if its evidence is missing from the final selection or the small
model call is unavailable.

Displayed scores are application-computed:

- **Impression Potential (0–90):** a relative opportunity heuristic based on final news
  strength and independent evidence count;
- **Model Confidence (0–65):** evidence quality, editorial confidence, source diversity,
  and corroboration.

Neither is an impression forecast in absolute numbers. The confidence cap remains
until approved first-party post analytics can calibrate the heuristic against the
owner's actual audience.

## Persistence and exactly-once behavior

Postgres stores:

- run status and safe aggregate counts;
- one digest row per local date and recipient HMAC;
- the rendered pending outbox body;
- a snapshot of story fingerprints, source IDs, URLs, and positions;
- provider ID, status, timestamps, and redacted error category.

Delivery flow:

1. Atomically insert a `pending` digest under a unique `(date, recipient_hmac)` key.
2. Send using `ai-digest/{recipient_hmac}/{date}` as the Resend idempotency key.
3. Mark the row `sent` with the provider message ID.
4. After a crash, reuse the stored body and the same idempotency key.
5. After 24 hours, the database unique constraint remains the source of truth.

Production aborts when the database schema is unavailable. It never sends first and
tries to remember later.

For a list of up to ten recipients, the pipeline renders one edition and creates every
recipient outbox row before provider contact. Addresses stay in process memory only;
the public logs and private database use safe counts and keyed fingerprints. Adding a
recipient later that day clones the persisted edition instead of recollecting or
calling the LLM. Conflicting stored payloads fail closed.

## Failure policy

| Failure | Behavior |
|---|---|
| One feed/sitemap fails | Record degraded source; continue |
| Fewer than five adapters are healthy | Abort |
| Missing X/Reddit credentials | Explicitly skip; never scrape |
| 429/5xx/timeouts | Bounded retry with backoff and jitter |
| Oversized response | Abort that source |
| Invalid model JSON/IDs | Try configured fallback, then deterministic editorial |
| No credible unsent stories | Abort without email |
| Database unavailable | Abort before delivery |
| Resend failure | Keep/mark pending digest for identical retry |
| Duplicate daily invocation | Return `already_sent`; no provider call |
| Healthcheck unavailable | Log safe warning; do not alter send outcome |

## Package map

```text
src/finalboss/
├── cli.py
├── config.py
├── pipeline.py
├── models.py
├── http.py
├── sources/
│   ├── feeds.py
│   ├── sitemaps.py
│   ├── reddit.py
│   └── x.py
├── processing/
│   ├── normalize.py
│   ├── dedupe.py
│   └── rank.py
├── llm/editor.py
├── storage/database.py
└── email/
    ├── renderer.py
    ├── resend.py
    └── templates/
```
