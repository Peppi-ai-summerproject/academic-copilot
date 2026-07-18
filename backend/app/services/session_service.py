from datetime import UTC, datetime

from app.schemas.session import UserSession


class SessionService:
    def __init__(self) -> None:
        self._sessions: dict[int, UserSession] = {}

    def get_or_create_session(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        username: str | None,
    ) -> UserSession:
        session = self._sessions.get(telegram_user_id)

        if session is not None:
            return session

        now = datetime.now(UTC)

        session = UserSession(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
            message_count=0,
            last_message=None,
            current_context=None,
            created_at=now,
            updated_at=now,
        )

        self._sessions[telegram_user_id] = session

        return session

    def update_session_message(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        username: str | None,
        message: str,
    ) -> UserSession:
        session = self.get_or_create_session(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
        )

        session.telegram_chat_id = telegram_chat_id
        session.username = username
        session.message_count += 1
        session.last_message = message
        session.updated_at = datetime.now(UTC)

        return session

    def get_session(
        self,
        telegram_user_id: int,
    ) -> UserSession | None:
        return self._sessions.get(telegram_user_id)

    def delete_session(
        self,
        telegram_user_id: int,
    ) -> bool:
        return self._sessions.pop(
            telegram_user_id,
            None,
        ) is not None


session_service = SessionService()