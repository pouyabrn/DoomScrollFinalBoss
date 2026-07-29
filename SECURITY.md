# Security policy

## Supported versions

Security fixes target the latest release on `main`.

## Report a vulnerability

Please use GitHub private vulnerability reporting for this repository. Do not open a
public issue containing a credential, recipient address, private feed URL, rendered
production email, database URL, provider response, or exploit details.

Include the affected revision, impact, safe reproduction steps, and any suggested
mitigation. You should receive an acknowledgement within seven days.

## Security model

- The repository and source registry are public.
- Credentials, recipient/sender values, private preferences, and healthcheck URLs are
  deployment secrets.
- X and Reddit use official authenticated APIs only.
- Source content is untrusted, bounded, stripped of markup, and cannot invoke tools.
- Model output is strict-schema validated and cannot provide links.
- The private database and Resend idempotency key jointly prevent duplicate sends.
- Production email bodies and database files are never uploaded as Actions artifacts.

See [docs/PRIVACY.md](docs/PRIVACY.md) for the trust boundary and retention details.
