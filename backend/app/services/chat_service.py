import logging

from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


class ChatService:
    async def process_message(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
        logger.info(
            "Processing chat message: user_id=%s chat_id=%s username=%s",
            request.telegram_user_id,
            request.telegram_chat_id,
            request.username,
        )

        reply = (
            "Backend received your message successfully.\n\n"
            f"Message: {request.message}"
        )

        return ChatResponse(reply=reply)


chat_service = ChatService()