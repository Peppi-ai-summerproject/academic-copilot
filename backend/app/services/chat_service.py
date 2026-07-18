import logging

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.session_service import session_service

logger = logging.getLogger(__name__)


class ChatService:
    async def process_message(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
        session = session_service.update_session_message(
            telegram_user_id=request.telegram_user_id,
            telegram_chat_id=request.telegram_chat_id,
            username=request.username,
            message=request.message,
        )

        logger.info(
            "Processing chat message: "
            "user_id=%s chat_id=%s username=%s message_count=%s",
            request.telegram_user_id,
            request.telegram_chat_id,
            request.username,
            session.message_count,
        )

        reply = (
            "Backend received your message successfully.\n\n"
            f"Message: {request.message}\n"
            f"Session message count: {session.message_count}"
        )

        session_service.add_assistant_message(
            telegram_user_id=request.telegram_user_id,
            reply=reply,
        )

        return ChatResponse(reply=reply)


chat_service = ChatService()