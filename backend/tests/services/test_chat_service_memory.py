from __future__ import annotations

import asyncio

from app.agents.state import AgentState
from app.agents.types import WorkflowStatus
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.conversation_memory import InMemoryConversationMemoryStore
from app.services.session_service import SessionService


class RecordingWorkflow:
    def __init__(self, status=WorkflowStatus.COMPLETED, raises=False):
        self.status = status
        self.raises = raises
        self.states: list[AgentState] = []

    async def run(self, state: AgentState) -> AgentState:
        self.states.append(state.model_copy(deep=True))
        if self.raises:
            raise RuntimeError("database password=secret")
        state.workflow_status = self.status
        state.final_response = "Safe current response"
        return state


class FailingStore(InMemoryConversationMemoryStore):
    fail_load = False
    fail_save = False

    def load(self, scope):
        if self.fail_load:
            raise RuntimeError("internal-db password=secret")
        return super().load(scope)

    def save_turn(self, scope, **kwargs):
        if self.fail_save:
            raise RuntimeError("internal-db password=secret")
        return super().save_turn(scope, **kwargs)


def request(**changes):
    values = {
        "message": "Check progress",
        "telegram_user_id": 101,
        "telegram_chat_id": 202,
        "student_id": 42,
        "selected_agents": ["communication"],
    }
    values.update(changes)
    return ChatRequest(**values)


def service(store, workflow=None):
    flow = workflow or RecordingWorkflow()
    return ChatService(
        session_service=SessionService(), workflow=flow, memory_store=store
    ), flow


def run(chat_service, chat_request, trusted=True):
    return asyncio.run(
        chat_service.process_message(chat_request, trusted_telegram=trusted)
    )


def test_successful_second_interaction_receives_first_turn_through_agent_state():
    store = InMemoryConversationMemoryStore()
    first_service, _ = service(store)
    first = run(first_service, request(message="First"))

    second_service, second_workflow = service(store)
    second = run(second_service, request(message="Second"))

    assert second.conversation_id == first.conversation_id
    memory = second_workflow.states[0].memory
    assert memory is not None
    assert second_workflow.states[0].telegram_user_id is None
    assert second_workflow.states[0].telegram_chat_id is None
    assert [(item.role, item.content) for item in memory.messages] == [
        ("user", "First"), ("assistant", "Safe current response")
    ]


def test_authoritative_telegram_mapping_ignores_supplied_conversation_uuid():
    store = InMemoryConversationMemoryStore()
    chat_service, _ = service(store)
    supplied = request().model_copy(update={"conversation_id": __import__("uuid").uuid4()})

    response = run(chat_service, supplied)

    assert response.conversation_id != supplied.conversation_id


def test_unauthenticated_request_never_loads_or_saves_memory():
    store = FailingStore()
    store.fail_load = True
    store.fail_save = True
    chat_service, workflow = service(store)

    response = run(chat_service, request(), trusted=False)

    assert response.reply == "Safe current response"
    assert workflow.states[0].memory is None
    assert store._messages == {}


def test_missing_conversation_id_generates_new_isolated_uuid_for_direct_calls():
    store = InMemoryConversationMemoryStore()
    chat_service, _ = service(store)

    first = run(chat_service, request(), trusted=False)
    second = run(chat_service, request(), trusted=False)

    assert first.conversation_id != second.conversation_id


def test_failed_workflow_does_not_store_or_corrupt_previous_memory():
    store = InMemoryConversationMemoryStore()
    good_service, _ = service(store)
    run(good_service, request(message="Good"))
    before = dict(store._messages)
    failed_service, _ = service(store, RecordingWorkflow(raises=True))

    response = run(failed_service, request(message="Bad"))

    assert "Please try again" in response.reply
    assert store._messages == before


def test_partial_workflow_stores_only_conversational_text_and_status():
    store = InMemoryConversationMemoryStore()
    chat_service, _ = service(store, RecordingWorkflow(WorkflowStatus.PARTIAL))

    run(chat_service, request())
    memory_scope = next(iter(store._messages))
    messages = store.load(memory_scope).messages

    assert [item.interaction_status for item in messages] == ["partial", "partial"]
    assert all("AgentResult" not in item.content for item in messages)


def test_load_failure_uses_empty_context_and_save_failure_preserves_response():
    store = FailingStore()
    store.fail_load = True
    store.fail_save = True
    chat_service, workflow = service(store)

    response = run(chat_service, request())

    assert response.reply == "Safe current response"
    assert workflow.states[0].memory is None


def test_stored_messages_exclude_state_results_errors_tokens_and_request_ids():
    store = InMemoryConversationMemoryStore()
    chat_service, _ = service(store)
    run(chat_service, request())
    stored = store._messages
    text = repr(stored)

    for forbidden in ("request_id", "agent_results", "MCP", "RAG", "token", "password"):
        assert forbidden not in text


def test_general_fallback_turn_is_stored_once_in_trusted_memory():
    store = InMemoryConversationMemoryStore()
    chat_service, workflow = service(store)

    response = run(
        chat_service,
        request(message="Hi", student_id=None, selected_agents=[]),
    )

    memory_scope = next(iter(store._messages))
    messages = store.load(memory_scope).messages
    assert [(item.role, item.content) for item in messages] == [
        ("user", "Hi"),
        ("assistant", response.reply),
    ]
    assert workflow.states == []
