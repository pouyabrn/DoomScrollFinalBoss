# Email boundary

- The production recipient list and sender come only from secrets.
- Send exactly one address per provider request. Never use CC/BCC or reveal recipients to each other.
- Never log or upload the rendered production body, subject, recipient, provider payload, or raw response.
- Render a multipart-equivalent HTML and plain-text body.
- Escape every source/model field. Links come only from validated application records.
- Use table-based, 600-640px email markup, inline CSS, no JavaScript, no remote fonts, and no tracking pixels.
- Keep Resend open/click tracking disabled at the domain level.
- The original provider call uses `ai-digest/{recipient_hmac}/{local-date}` as its stable
  idempotency key. An intentional resend uses the database-reserved
  `/resend-{sequence}` suffix and must reuse that key after a failed or interrupted attempt.
- Continue through independent recipient failures, then fail the batch with safe aggregate counts.
- Visual template changes require HTML-escaping tests, a text snapshot, and manual Gmail/Outlook/Apple Mail review.
