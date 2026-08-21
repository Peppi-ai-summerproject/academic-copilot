from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.conversation_memory import (
    MemoryScope,
    SQLAlchemyConversationMemoryStore,
)


def scope() -> MemoryScope:
    return MemoryScope(
        conversation_id=uuid4(),
        owner_type="telegram",
        owner_reference="user:1:chat:2",
        student_id=42,
    )


def test_save_locks_exact_scope_before_atomic_insert_and_retention():
    session = MagicMock()
    store = SQLAlchemyConversationMemoryStore(lambda: session)

    store.save_turn(
        scope(),
        user_message="user",
        assistant_message="assistant",
        selected_agents=["progress"],
        interaction_status="completed",
    )

    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert "pg_advisory_xact_lock" in statements[0]
    assert "INSERT INTO conversation_memory_messages" in statements[1]
    assert "INSERT INTO conversation_memory_messages" in statements[2]
    assert "DELETE FROM conversation_memory_messages" in statements[3]
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()
    session.close.assert_called_once_with()


def test_second_insert_failure_rolls_back_entire_turn():
    session = MagicMock()
    session.execute.side_effect = [MagicMock(), MagicMock(), RuntimeError("write failed")]
    store = SQLAlchemyConversationMemoryStore(lambda: session)

    with pytest.raises(RuntimeError, match="write failed"):
        store.save_turn(
            scope(),
            user_message="user",
            assistant_message="assistant",
            selected_agents=[],
            interaction_status="completed",
        )

    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_concurrent_mapping_conflict_reloads_only_the_exact_pair():
    concurrent_id = uuid4()
    session = MagicMock()
    missing = MagicMock()
    missing.scalar_one_or_none.return_value = None
    conflict = IntegrityError("insert", {}, Exception("unique conflict"))
    concurrent = MagicMock()
    concurrent.scalar_one.return_value = concurrent_id
    session.execute.side_effect = [missing, conflict, concurrent]
    store = SQLAlchemyConversationMemoryStore(lambda: session)

    resolved = store.resolve_telegram_conversation(10, 20)

    assert resolved == concurrent_id
    session.rollback.assert_called_once_with()
    final_params = session.execute.call_args_list[-1].args[1]
    assert final_params == {"user_id": 10, "chat_id": 20}
    session.close.assert_called_once_with()


def test_load_restores_latest_canonical_entity_context():
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {
            "role": "user",
            "content": "Show DIN24",
            "interaction_status": "completed",
            "created_at": datetime.now(UTC),
            "resolved_entities": [
                {"entity_type": "COURSE", "status": "RESOLVED", "canonical_id": 24}
            ],
        }
    ]
    session.execute.return_value = result

    snapshot = SQLAlchemyConversationMemoryStore(lambda: session).load(scope())

    assert snapshot.resolved_entities[0]["canonical_id"] == 24
