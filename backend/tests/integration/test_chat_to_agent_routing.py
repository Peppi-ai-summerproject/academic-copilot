"""Integration coverage from ChatRequest through routing to workflow boundary."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import FastAPI
import httpx
import pytest

from app.agents.registry import AgentRegistry
from app.agents.routing import SUPPORTED_ROUTES
from app.agents.state import AgentState
from app.agents.types import AgentResult, WorkflowStatus
from app.api.routes import chat
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.conversation_memory import InMemoryConversationMemoryStore
from app.services.session_service import SessionService


PLACEHOLDER = "Backend received your message successfully."


class DummyAgent:
    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("Integration routing tests must not instantiate agents")


class RecordingWorkflow:
    def __init__(
        self,
        *,
        status: WorkflowStatus = WorkflowStatus.COMPLETED,
        final_response: object = "Authoritative tutor response",
        results: dict[str, AgentResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.final_response = final_response
        self.results = results or {}
        self.error = error
        self.states: list[AgentState] = []

    async def run(self, state: AgentState) -> AgentState:
        self.states.append(state.model_copy(deep=True))
        if self.error is not None:
            raise self.error
        state.workflow_status = self.status
        state.final_response = self.final_response  # type: ignore[assignment]
        state.agent_results = self.results
        return state


def registry(*routes: str) -> AgentRegistry:
    registered = AgentRegistry()
    for route in routes:
        registered.register(route, DummyAgent)  # type: ignore[arg-type]
    return registered


def complete_registry() -> AgentRegistry:
    return registry(*(route for route in SUPPORTED_ROUTES if route != "finish"))


def request(**changes) -> ChatRequest:
    values = {
        "message": "How is student 123 progressing?",
        "student_id": 123,
        "telegram_user_id": 101,
        "telegram_chat_id": 202,
        "username": "tutor",
    }
    values.update(changes)
    return ChatRequest(**values)


def service(
    workflow: RecordingWorkflow,
    *,
    active_registry: AgentRegistry | None = None,
    sessions: SessionService | None = None,
    memory_store: InMemoryConversationMemoryStore | None = None,
) -> tuple[ChatService, SessionService]:
    session_service = sessions or SessionService()
    return (
        ChatService(
            session_service=session_service,
            workflow=workflow,
            registry=active_registry or complete_registry(),
            memory_store=memory_store,
        ),
        session_service,
    )


def process(chat_service: ChatService, chat_request: ChatRequest, *, trusted=False):
    return asyncio.run(
        chat_service.process_message(chat_request, trusted_telegram=trusted)
    )


@pytest.mark.parametrize(
    ("message", "intent", "expected_routes"),
    [
        ("How is student 123 progressing?", "progress", ["progress"]),
        ("Is student 123 at risk?", "risk", ["risk"]),
        (
            "What should I do to help this student?",
            "recommendation",
            ["risk", "recommendation"],
        ),
        (
            "Give me an academic summary of student 123.",
            "reporting",
            ["progress", "study_rights", "risk", "recommendation", "reporting"],
        ),
    ],
)
def test_natural_academic_request_reaches_workflow_with_exact_plan(
    message: str,
    intent: str,
    expected_routes: list[str],
) -> None:
    workflow = RecordingWorkflow()
    chat_service, _ = service(workflow)
    chat_request = request(message=message)

    assert chat_request.selected_agents == []
    response = process(chat_service, chat_request)

    assert len(workflow.states) == 1
    state = workflow.states[0]
    assert state.intent == intent
    assert state.selected_agents == expected_routes
    assert state.student_id == 123
    assert response.reply == "Authoritative tutor response"
    assert PLACEHOLDER not in response.reply
    assert len(state.selected_agents) == len(set(state.selected_agents))


def test_valid_final_response_precedes_internal_agent_summaries() -> None:
    result = AgentResult(
        agent_name="ProgressAnalysisAgent",
        route="progress",
        status="SUCCESS",
        summary="Internal progress summary",
    )
    workflow = RecordingWorkflow(results={"progress": result})
    chat_service, _ = service(workflow)

    response = process(chat_service, request())

    assert response.reply == "Authoritative tutor response"
    assert "Internal progress summary" not in response.reply


def test_explicit_routes_preserve_order_and_bypass_automatic_intent() -> None:
    workflow = RecordingWorkflow()
    chat_service, _ = service(workflow)

    response = process(
        chat_service,
        request(
            message="Is student 123 at risk?",
            selected_agents=["study_rights", "progress"],
        ),
    )

    assert workflow.states[0].intent is None
    assert workflow.states[0].selected_agents == ["study_rights", "progress"]
    assert response.reply == "Authoritative tutor response"


@pytest.mark.parametrize(
    ("message", "response_fragment"),
    [
        ("Hi", "academic copilot"),
        ("What can you help me with?", "study rights"),
        ("Check this student.", "clarify"),
        ("What's the weather today?", "focused on"),
    ],
)
def test_non_workflow_requests_return_user_fallback_without_execution(
    message: str,
    response_fragment: str,
) -> None:
    workflow = RecordingWorkflow()
    chat_service, _ = service(workflow)

    response = process(
        chat_service,
        request(message=message, student_id=None),
    )

    assert workflow.states == []
    assert response_fragment in response.reply.lower()
    assert PLACEHOLDER not in response.reply


def test_missing_student_context_stops_workflow_without_guessing() -> None:
    workflow = RecordingWorkflow()
    chat_service, _ = service(workflow)

    response = process(
        chat_service,
        request(message="Is the student at risk?", student_id=None),
    )

    assert workflow.states == []
    assert "student identifier" in response.reply.lower()


def test_unregistered_automatic_route_fails_before_workflow() -> None:
    workflow = RecordingWorkflow()
    chat_service, _ = service(workflow, active_registry=AgentRegistry())

    response = process(chat_service, request(message="Is student 123 at risk?"))

    assert workflow.states == []
    assert "prepare the academic analysis safely" in response.reply


def test_failed_workflow_ignores_stale_internal_final_response() -> None:
    workflow = RecordingWorkflow(
        status=WorkflowStatus.FAILED,
        final_response="AgentState(traceback database password=secret)",
    )
    chat_service, _ = service(workflow)

    response = process(chat_service, request())

    assert "could not be completed" in response.reply
    for forbidden in ("AgentState", "traceback", "password"):
        assert forbidden not in response.reply


def test_workflow_exception_is_controlled_at_chat_boundary() -> None:
    workflow = RecordingWorkflow(error=RuntimeError("database password=secret"))
    chat_service, _ = service(workflow)

    response = process(chat_service, request())

    assert response.reply == "I could not complete the academic analysis. Please try again."
    assert "password" not in response.reply


def test_partial_workflow_preserves_qualified_available_response() -> None:
    partial = (
        "Verified progress information is available.\n\n"
        "Availability note: risk information could not be verified."
    )
    workflow = RecordingWorkflow(
        status=WorkflowStatus.PARTIAL,
        final_response=partial,
    )
    chat_service, _ = service(workflow)

    response = process(chat_service, request())

    assert response.reply == partial
    assert "Availability note" in response.reply


def test_session_conversation_and_trusted_memory_store_delivered_reply_once() -> None:
    workflow = RecordingWorkflow()
    sessions = SessionService()
    memory = InMemoryConversationMemoryStore()
    chat_service, _ = service(
        workflow,
        sessions=sessions,
        memory_store=memory,
    )

    first = process(chat_service, request(), trusted=True)
    second = process(chat_service, request(message="How is this student progressing?"), trusted=True)

    assert second.conversation_id == first.conversation_id
    session = sessions.get_session(101)
    assert session is not None
    assert session.message_count == 2
    assert [item.role for item in session.history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert session.history[-1].content == second.reply
    stored = memory.load(next(iter(memory._messages))).messages
    assert [item.content for item in stored] == [
        "How is student 123 progressing?",
        "Authoritative tutor response",
        "How is this student progressing?",
        "Authoritative tutor response",
    ]


def test_chat_api_natural_request_returns_workflow_reply(monkeypatch) -> None:
    workflow = RecordingWorkflow(final_response="API tutor response")
    chat_service, _ = service(workflow)
    monkeypatch.setattr(chat, "chat_service", chat_service)
    app = FastAPI()
    app.include_router(chat.router, prefix="/api/v1/chat")

    async def post_request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://chat.test",
        ) as client:
            return await client.post(
                "/api/v1/chat/messages",
                json=request(conversation_id=uuid4()).model_dump(mode="json"),
            )

    response = asyncio.run(post_request())

    assert response.status_code == 200
    assert response.json()["reply"] == "API tutor response"
    assert PLACEHOLDER not in response.json()["reply"]
    assert workflow.states[0].intent == "progress"
    assert workflow.states[0].selected_agents == ["progress"]
