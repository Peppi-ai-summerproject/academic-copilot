from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Callable, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.memory import ConversationMemorySnapshot, MemoryMessage


MAX_MEMORY_MESSAGES = 20
MAX_MEMORY_MESSAGE_LENGTH = 4000


@dataclass(frozen=True)
class MemoryScope:
    conversation_id: UUID
    owner_type: str
    owner_reference: str
    student_id: int | None


class ConversationMemoryStore(Protocol):
    def resolve_telegram_conversation(self, user_id: int, chat_id: int) -> UUID: ...
    def load(self, scope: MemoryScope) -> ConversationMemorySnapshot: ...
    def save_turn(
        self,
        scope: MemoryScope,
        *,
        user_message: str,
        assistant_message: str,
        selected_agents: list[str],
        interaction_status: str,
        resolved_entities: list[dict] | None = None,
    ) -> None: ...


def telegram_owner_reference(user_id: int, chat_id: int) -> str:
    return f"user:{user_id}:chat:{chat_id}"


class InMemoryConversationMemoryStore:
    """Deterministic test implementation of the production memory contract."""

    def __init__(self) -> None:
        self._mappings: dict[tuple[int, int], UUID] = {}
        self._messages: dict[MemoryScope, list[MemoryMessage]] = {}
        self._entities: dict[MemoryScope, list[dict]] = {}

    def resolve_telegram_conversation(self, user_id: int, chat_id: int) -> UUID:
        return self._mappings.setdefault((user_id, chat_id), uuid4())

    def load(self, scope: MemoryScope) -> ConversationMemorySnapshot:
        return ConversationMemorySnapshot(
            conversation_id=scope.conversation_id,
            student_id=scope.student_id,
            messages=list(self._messages.get(scope, [])),
            resolved_entities=list(self._entities.get(scope, [])),
        )

    def save_turn(
        self,
        scope: MemoryScope,
        *,
        user_message: str,
        assistant_message: str,
        selected_agents: list[str],
        interaction_status: str,
        resolved_entities: list[dict] | None = None,
    ) -> None:
        del selected_agents
        if interaction_status not in {"completed", "partial"}:
            return
        now = datetime.now(UTC)
        messages = self._messages.setdefault(scope, [])
        messages.extend([
            MemoryMessage(role="user", content=_bounded_text(user_message), interaction_status=interaction_status, created_at=now),
            MemoryMessage(role="assistant", content=_bounded_text(assistant_message), interaction_status=interaction_status, created_at=now),
        ])
        self._messages[scope] = messages[-MAX_MEMORY_MESSAGES:]
        if resolved_entities:
            self._entities[scope] = list(resolved_entities)


class SQLAlchemyConversationMemoryStore:
    """PostgreSQL store; schema is installed manually by deployment operators."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def resolve_telegram_conversation(self, user_id: int, chat_id: int) -> UUID:
        session = self._session_factory()
        try:
            existing = session.execute(
                text("""
                    SELECT conversation_id FROM telegram_conversation_mappings
                    WHERE telegram_user_id = :user_id AND telegram_chat_id = :chat_id
                """),
                {"user_id": user_id, "chat_id": chat_id},
            ).scalar_one_or_none()
            if existing is not None:
                return UUID(str(existing))
            conversation_id = uuid4()
            try:
                session.execute(
                    text("""
                        INSERT INTO telegram_conversation_mappings
                            (telegram_user_id, telegram_chat_id, conversation_id)
                        VALUES (:user_id, :chat_id, :conversation_id)
                    """),
                    {"user_id": user_id, "chat_id": chat_id, "conversation_id": conversation_id},
                )
                session.commit()
                return conversation_id
            except IntegrityError:
                session.rollback()
                concurrent = session.execute(
                    text("""
                        SELECT conversation_id FROM telegram_conversation_mappings
                        WHERE telegram_user_id = :user_id AND telegram_chat_id = :chat_id
                    """),
                    {"user_id": user_id, "chat_id": chat_id},
                ).scalar_one()
                return UUID(str(concurrent))
        finally:
            session.close()

    def load(self, scope: MemoryScope) -> ConversationMemorySnapshot:
        session = self._session_factory()
        try:
            rows = session.execute(
                text("""
                    SELECT role, content, interaction_status, created_at, resolved_entities
                    FROM (
                        SELECT id, role, content, interaction_status, created_at, resolved_entities
                        FROM conversation_memory_messages
                        WHERE conversation_id = :conversation_id
                          AND owner_type = :owner_type
                          AND owner_reference = :owner_reference
                          AND student_id IS NOT DISTINCT FROM :student_id
                        ORDER BY id DESC LIMIT :limit
                    ) AS recent_messages
                    ORDER BY id ASC
                """),
                {**_scope_params(scope), "limit": MAX_MEMORY_MESSAGES},
            ).mappings().all()
            entities = next(
                (
                    list(row["resolved_entities"])
                    for row in reversed(rows)
                    if row.get("resolved_entities")
                ),
                [],
            )
            return ConversationMemorySnapshot(
                conversation_id=scope.conversation_id,
                student_id=scope.student_id,
                messages=[
                    MemoryMessage.model_validate(
                        {
                            key: row[key]
                            for key in (
                                "role",
                                "content",
                                "interaction_status",
                                "created_at",
                            )
                        }
                    )
                    for row in rows
                ],
                resolved_entities=entities,
            )
        finally:
            session.close()

    def save_turn(
        self,
        scope: MemoryScope,
        *,
        user_message: str,
        assistant_message: str,
        selected_agents: list[str],
        interaction_status: str,
        resolved_entities: list[dict] | None = None,
    ) -> None:
        if interaction_status not in {"completed", "partial"}:
            return
        session = self._session_factory()
        try:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope_key, 0))"),
                {"scope_key": _scope_lock_key(scope)},
            )
            params = {
                **_scope_params(scope),
                "selected_agents": json.dumps(selected_agents),
                "interaction_status": interaction_status,
                "resolved_entities": json.dumps(resolved_entities or []),
            }
            for role, content in (("user", user_message), ("assistant", assistant_message)):
                session.execute(
                    text("""
                        INSERT INTO conversation_memory_messages
                            (conversation_id, owner_type, owner_reference, student_id,
                             role, content, selected_agents, interaction_status, resolved_entities)
                        VALUES (:conversation_id, :owner_type, :owner_reference, :student_id,
                                :role, :content, CAST(:selected_agents AS JSONB), :interaction_status,
                                CAST(:resolved_entities AS JSONB))
                    """),
                    {**params, "role": role, "content": _bounded_text(content)},
                )
            session.execute(
                text("""
                    DELETE FROM conversation_memory_messages
                    WHERE id IN (
                        SELECT id FROM conversation_memory_messages
                        WHERE conversation_id = :conversation_id
                          AND owner_type = :owner_type
                          AND owner_reference = :owner_reference
                          AND student_id IS NOT DISTINCT FROM :student_id
                        ORDER BY id DESC OFFSET :limit
                    )
                """),
                {**_scope_params(scope), "limit": MAX_MEMORY_MESSAGES},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _scope_params(scope: MemoryScope) -> dict[str, object]:
    return {
        "conversation_id": scope.conversation_id,
        "owner_type": scope.owner_type,
        "owner_reference": scope.owner_reference,
        "student_id": scope.student_id,
    }


def _bounded_text(value: str) -> str:
    return value[:MAX_MEMORY_MESSAGE_LENGTH]


def _scope_lock_key(scope: MemoryScope) -> str:
    student_partition = str(scope.student_id) if scope.student_id is not None else "NULL"
    return "|".join((
        str(scope.conversation_id),
        scope.owner_type,
        scope.owner_reference,
        student_partition,
    ))
