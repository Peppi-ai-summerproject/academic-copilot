from datetime import UTC, datetime

from app.schemas.session import ConversationMessage, UserSession


MAX_HISTORY_MESSAGES = 20


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
            history=[],
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

        self.add_history_message(
            session=session,
            role="user",
            content=message,
        )

        return session

    def add_assistant_message(
        self,
        *,
        telegram_user_id: int,
        reply: str,
    ) -> UserSession | None:
        session = self.get_session(telegram_user_id)

        if session is None:
            return None

        self.add_history_message(
            session=session,
            role="assistant",
            content=reply,
        )

        return session

    def add_history_message(
        self,
        *,
        session: UserSession,
        role: str,
        content: str,
    ) -> None:
        session.history.append(
            ConversationMessage(
                role=role,
                content=content,
                created_at=datetime.now(UTC),
            )
        )

        if len(session.history) > MAX_HISTORY_MESSAGES:
            session.history = session.history[-MAX_HISTORY_MESSAGES:]

        session.updated_at = datetime.now(UTC)

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