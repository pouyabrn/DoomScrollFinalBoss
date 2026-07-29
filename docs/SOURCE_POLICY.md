# Source policy

## Accepted sources

A source must be one of:

- publisher-provided RSS/Atom;
- official public sitemap metadata;
- documented official API under an approved use case;
- a manually maintained public fixture used only in tests.

Each entry needs a stable ID, name, HTTPS URL, category, trust tier, weight, bounded
item count, and terms note.

## Not accepted

- X/Reddit scraping, browser automation, Nitter, RSSHub bypasses, or undocumented JSON;
- paywall/authentication/captcha bypass;
- generic crawling that ignores publisher rules;
- copying full copyrighted article bodies;
- personal/private feeds committed to the public registry;
- sources whose main function is rumor or engagement farming.

## Trust tiers

| Tier | Use |
|---|---|
| `primary` | Official lab/vendor/project announcement |
| `research` | Paper/publication feed |
| `expert` | Identified expert newsletter/commentary |
| `press` | Journalism and secondary reporting |
| `social` | Ephemeral corroboration only |

Weights tune authority within a tier. A high social score cannot outweigh weak evidence
because social engagement is logarithmically capped.

## Current coverage

The registry covers:

- official lab/platform sources including OpenAI, Anthropic, Google DeepMind, Google
  AI, Microsoft, Mistral, Cohere, Stability AI, Hugging Face, NVIDIA, AWS, GitHub,
  Cloudflare, Mozilla, and OpenRouter;
- arXiv AI, language, and machine-learning feeds;
- Import AI, Interconnects, Latent Space, One Useful Thing, Normal Technology, Ahead of
  AI, SemiAnalysis, Last Week in AI, The Gradient, The Algorithmic Bridge, Ben’s Bites,
  and Simon Willison;
- a small lower-weight press layer for corroboration.

Source presence does not guarantee inclusion. Ranking, freshness, deduplication,
evidence quality, and the top-20 limit decide each edition.
