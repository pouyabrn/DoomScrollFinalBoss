# Source adapter boundary

- X and Reddit are official API only. Never add HTML scraping, browser automation, Nitter, RSSHub, unauthenticated `.json`, or other bypasses.
- Missing social credentials are a normal, explicit degraded state. Fail closed and report `skipped`.
- Social posts are corroboration/discovery only. Do not send raw comments, self-post bodies, or usernames to the LLM, email provider, logs, or persistent storage.
- Prefer publisher RSS/Atom. Do not bypass paywalls, robots rules, authentication, or publisher blocks.
- Sitemap adapters may read URL and `lastmod` metadata only; they do not fetch article bodies.
- Bound requests by time, bytes, concurrency, redirects, and item count.
- A broken source must not take down healthy sources.
- New adapters require contract tests for success, timeout, malformed data, authentication failure, and rate limiting.
