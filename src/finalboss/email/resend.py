from __future__ import annotations

from finalboss.http import BoundedHttpClient
from finalboss.models import RenderedDigest


class ResendSender:
    API_URL = "https://api.resend.com/emails"

    def __init__(self, client: BoundedHttpClient, *, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def send(
        self,
        rendered: RenderedDigest,
        *,
        sender: str,
        recipient: str,
        idempotency_key: str,
    ) -> str:
        response = await self._client.post_json(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Idempotency-Key": idempotency_key,
            },
            json_body={
                "from": sender,
                "to": [recipient],
                "subject": rendered.subject,
                "html": rendered.html,
                "text": rendered.text,
                "tags": [{"name": "kind", "value": "daily-ai-digest"}],
            },
            attempts=3,
        )
        message_id = response.get("id")
        if not isinstance(message_id, str) or not message_id:
            raise ValueError("email provider returned no message ID")
        return message_id
