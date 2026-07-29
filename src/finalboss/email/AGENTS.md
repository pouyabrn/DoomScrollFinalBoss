# Email boundary

- The production recipient and sender come only from secrets.
- Never log or upload the rendered production body, subject, recipient, provider payload, or raw response.
- Render a multipart-equivalent HTML and plain-text body.
- Escape every source/model field. Links come only from validated application records.
- Use table-based, 600-640px email markup, inline CSS, no JavaScript, no remote fonts, and no tracking pixels.
- Keep Resend open/click tracking disabled at the domain level.
- Every provider call uses `ai-digest/{recipient_hmac}/{local-date}` as its stable idempotency key.
- Visual template changes require HTML-escaping tests, a text snapshot, and manual Gmail/Outlook/Apple Mail review.
