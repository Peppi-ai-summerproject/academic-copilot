import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackendClientError(Exception):
    """Raised when communication with the backend fails."""


class BackendClient:
    def __init__(self) -> None:
        self.base_url = settings.backend_base_url.rstrip("/")

    async def send_message(
        self,
        *,
        message: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        username: str | None,
    ) -> str:
        url = f"{self.base_url}/api/v1/chat/messages"

        payload = {
            "message": message,
            "telegram_user_id": telegram_user_id,
            "telegram_chat_id": telegram_chat_id,
            "username": username,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

        except httpx.HTTPError as exc:
            logger.exception(
                "Failed to communicate with backend: url=%s",
                url,
            )
            raise BackendClientError(
                "Backend communication failed."
            ) from exc

        data = response.json()
        reply = data.get("reply")

        if not isinstance(reply, str):
            raise BackendClientError(
                "Backend returned an invalid response."
            )

        return reply


backend_client = BackendClient()