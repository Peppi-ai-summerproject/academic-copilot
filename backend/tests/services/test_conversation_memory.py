from __future__ import annotations

import json
from uuid import uuid4

from app.services.conversation_memory import (
    InMemoryConversationMemoryStore,
    MemoryScope,
    telegram_owner_reference,
)


def scope(*, conversation=None, owner="user:1:chat:2", student=42):
    return MemoryScope(
        conversation_id=conversation or uuid4(),
        owner_type="telegram",
        owner_reference=owner,
        student_id=student,
    )


def save(store, memory_scope, number, status="completed"):
    store.save_turn(
        memory_scope,
        user_message=f"user-{number}",
        assistant_message=f"assistant-{number}",
        selected_agents=["progress"],
        interaction_status=status,
    )


def test_exact_telegram_pair_reuses_mapping_and_pairs_are_isolated():
    store = InMemoryConversationMemoryStore()

    first = store.resolve_telegram_conversation(1, 10)

    assert store.resolve_telegram_conversation(1, 10) == first
    assert store.resolve_telegram_conversation(2, 10) != first
    assert store.resolve_telegram_conversation(1, 11) != first


def test_conversation_owner_and_student_partitions_are_isolated():
    store = InMemoryConversationMemoryStore()
    conversation = uuid4()
    original = scope(conversation=conversation)
    save(store, original, 1)

    assert len(store.load(original).messages) == 2
    assert store.load(scope(conversation=uuid4())).messages == []
    assert store.load(scope(conversation=conversation, owner="user:9:chat:2")).messages == []
    assert store.load(scope(conversation=conversation, student=99)).messages == []
    assert store.load(scope(conversation=conversation, student=None)).messages == []


def test_null_student_partition_is_exact_not_wildcard():
    store = InMemoryConversationMemoryStore()
    conversation = uuid4()
    null_scope = scope(conversation=conversation, student=None)
    save(store, null_scope, 1)

    assert len(store.load(null_scope).messages) == 2
    assert store.load(scope(conversation=conversation, student=42)).messages == []


def test_retention_keeps_newest_twenty_messages_in_oldest_first_order():
    store = InMemoryConversationMemoryStore()
    memory_scope = scope()

    for number in range(12):
        save(store, memory_scope, number)

    messages = store.load(memory_scope).messages
    assert len(messages) == 20
    assert [item.content for item in messages[:2]] == ["user-2", "assistant-2"]
    assert [item.content for item in messages[-2:]] == ["user-11", "assistant-11"]


def test_retention_does_not_delete_another_partition():
    store = InMemoryConversationMemoryStore()
    first = scope()
    second = scope()
    save(store, second, 99)
    for number in range(12):
        save(store, first, number)

    assert len(store.load(first).messages) == 20
    assert len(store.load(second).messages) == 2


def test_failed_status_is_not_stored_and_snapshot_is_json_serializable():
    store = InMemoryConversationMemoryStore()
    memory_scope = scope()
    save(store, memory_scope, 1, status="failed")

    snapshot = store.load(memory_scope)

    assert snapshot.messages == []
    json.dumps(snapshot.model_dump(mode="json"))


def test_owner_reference_contains_both_trusted_telegram_identifiers():
    assert telegram_owner_reference(12, 34) == "user:12:chat:34"


def test_message_text_is_bounded():
    store = InMemoryConversationMemoryStore()
    memory_scope = scope()
    store.save_turn(
        memory_scope,
        user_message="u" * 5000,
        assistant_message="a" * 5000,
        selected_agents=[],
        interaction_status="completed",
    )

    assert [len(item.content) for item in store.load(memory_scope).messages] == [4000, 4000]
