from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
import httpx
import pytest

from app.agents.state import AgentState
from app.agents.workflow import create_academic_agent_workflow
from app.api.routes import chat
from app.gateways.policy_context import PolicyContextResult, PolicyEvidenceCandidate
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.conversation_memory import InMemoryConversationMemoryStore
from app.services.session_service import SessionService
from app.telegram import backend_client as backend_client_module
from app.telegram import commands, handlers


PLACEHOLDER = "Backend received your message successfully"


class DeterministicAcademicGateway:
    def __init__(self, *, fail_progress: bool = False) -> None:
        self.fail_progress = fail_progress
        self.calls: list[tuple[str, int | None]] = []

    async def get_student(self, student_id: int):
        self.calls.append(("student", student_id))
        return {
            "success": True,
            "student": {
                "id": student_id,
                "name": "Test Student",
                "programme": "Software Engineering",
            },
        }

    async def get_progress(self, student_id: int):
        self.calls.append(("progress", student_id))
        if self.fail_progress:
            return {"success": False, "error": "PROGRESS_UNAVAILABLE"}
        return {
            "success": True,
            "progress": {
                "completed_ects": 80,
                "expected_ects": 120,
                "difference_ects": -40,
                "status": "BEHIND",
                "current_semester": 4,
                "progress_percentage": 66.67,
            },
        }

    async def get_study_right(self, student_id: int):
        self.calls.append(("study_right", student_id))
        return {
            "success": True,
            "study_right": {
                "status": "EXPIRES_SOON",
                "extension_count": 1,
                "is_expiring_soon": True,
                "expiration_date": "2026-12-31",
            },
        }

    async def get_upcoming_events(self):
        self.calls.append(("events", None))
        return {"success": True, "events": []}


class DeterministicPolicyGateway:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def retrieve_policy(self, query: str, *, top_k: int = 3):
        self.queries.append(query)
        return PolicyContextResult(
            query=query,
            candidates=(
                PolicyEvidenceCandidate(
                    chunk_id="policy-1",
                    text="Tutors should review confirmed academic delays.",
                    score=0.95,
                    source="test-policy",
                ),
            ),
        )


class ObservedWorkflow:
    def __init__(self, workflow) -> None:
        self.workflow = workflow
        self.inputs: list[AgentState] = []
        self.outputs: list[AgentState] = []

    async def run(self, state: AgentState) -> AgentState:
        self.inputs.append(state.model_copy(deep=True))
        result = await self.workflow.run(state)
        self.outputs.append(result.model_copy(deep=True))
        return result


class Harness:
    def __init__(self, app, service, workflow, gateway, sessions, memory) -> None:
        self.app = app
        self.service = service
        self.workflow = workflow
        self.gateway = gateway
        self.sessions = sessions
        self.memory = memory

    async def post(self, payload: dict):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://copilot.test",
        ) as client:
            return await client.post("/api/v1/chat/messages", json=payload)


@pytest.fixture
def harness(monkeypatch) -> Harness:
    gateway = DeterministicAcademicGateway()
    policies = DeterministicPolicyGateway()
    observed = ObservedWorkflow(
        create_academic_agent_workflow(gateway=gateway, policy_gateway=policies)
    )
    sessions = SessionService()
    memory = InMemoryConversationMemoryStore()
    service = ChatService(
        session_service=sessions,
        workflow=observed,
        memory_store=memory,
    )
    monkeypatch.setattr(chat, "chat_service", service)
    app = FastAPI()
    app.include_router(chat.router, prefix="/api/v1/chat")

    real_client = httpx.AsyncClient

    def backend_transport(*args, **kwargs):
        return real_client(
            transport=httpx.ASGITransport(app=app),
            base_url="http://copilot.test",
            timeout=kwargs.get("timeout", 10.0),
        )

    monkeypatch.setattr(backend_client_module.httpx, "AsyncClient", backend_transport)
    monkeypatch.setattr(backend_client_module.settings, "backend_base_url", "http://copilot.test")
    monkeypatch.setattr(backend_client_module.settings, "internal_service_key", "e2e-key")
    monkeypatch.setattr(chat.settings, "internal_service_key", "e2e-key")
    client = backend_client_module.BackendClient()
    monkeypatch.setattr(handlers, "backend_client", client)
    monkeypatch.setattr(commands, "backend_client", client)
    return Harness(app, service, observed, gateway, sessions, memory)


def payload(message: str, *, student_id: int | None = 123) -> dict:
    value = {
        "message": message,
        "telegram_user_id": 7001,
        "telegram_chat_id": 8001,
        "username": "e2e_tutor",
    }
    if student_id is not None:
        value["student_id"] = student_id
    return value


def update(text: str):
    message = SimpleNamespace(
        text=text,
        reply_text=AsyncMock(),
        reply_chat_action=AsyncMock(),
    )
    return SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(id=7001, username="e2e_tutor"),
        effective_chat=SimpleNamespace(id=8001),
    )


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("message", "intent", "routes"),
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
        (
            "Does student 123 have any important upcoming deadlines?",
            "calendar",
            ["calendar"],
        ),
    ],
)
def test_chat_api_runs_real_routing_workflow_and_agents(harness, message, intent, routes):
    response = asyncio.run(harness.post(payload(message)))

    assert response.status_code == 200
    assert PLACEHOLDER not in response.json()["reply"]
    assert "Academic analysis" in response.json()["reply"]
    assert harness.workflow.inputs[-1].intent == intent
    assert harness.workflow.inputs[-1].selected_agents == routes
    assert harness.workflow.outputs[-1].completed_agents == routes


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("Hi", "Academic Copilot"),
        ("Check this student.", "clarify"),
        ("What's the weather today?", "focused on"),
        ("Is the student at risk?", "student identifier"),
    ],
)
def test_telegram_text_fallbacks_cross_real_backend_without_agent_execution(
    harness, text, fragment
):
    before = len(harness.workflow.inputs)
    telegram_update = update(text)

    asyncio.run(handlers.handle_message(telegram_update, context=None))

    reply = telegram_update.message.reply_text.await_args.args[0]
    assert fragment.lower() in reply.lower()
    assert PLACEHOLDER not in reply
    assert len(harness.workflow.inputs) == before


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("command", "handler", "routes"),
    [
        ("progress", commands.progress_command, ["progress"]),
        ("risk", commands.risk_command, ["risk"]),
        ("events", commands.events_command, ["calendar"]),
        (
            "student",
            commands.student_command,
            ["progress", "study_rights", "risk", "recommendation", "reporting"],
        ),
    ],
)
def test_academic_commands_cross_backend_and_run_real_workflow(
    harness, command, handler, routes
):
    telegram_update = update(f"/{command} 123")

    asyncio.run(handler(telegram_update, SimpleNamespace(args=["123"])))

    reply = telegram_update.message.reply_text.await_args.args[0]
    assert PLACEHOLDER not in reply
    assert "Academic analysis" in reply
    assert harness.workflow.inputs[-1].student_id == 123
    assert harness.workflow.inputs[-1].selected_agents == routes


@pytest.mark.e2e
def test_invalid_command_does_not_reach_backend_workflow(harness):
    telegram_update = update("/risk invalid")

    asyncio.run(commands.risk_command(telegram_update, SimpleNamespace(args=["invalid"])))

    assert "valid positive student ID" in telegram_update.message.reply_text.await_args.args[0]
    assert harness.workflow.inputs == []


@pytest.mark.e2e
def test_multi_message_command_conversation_preserves_session_and_memory(harness):
    for command, handler in (
        ("progress", commands.progress_command),
        ("risk", commands.risk_command),
    ):
        asyncio.run(handler(update(f"/{command} 123"), SimpleNamespace(args=["123"])))

    session = harness.sessions.get_session(7001)
    assert session is not None
    assert session.message_count == 2
    assert [item.role for item in session.history] == [
        "user", "assistant", "user", "assistant"
    ]
    scopes = list(harness.memory._messages)
    assert len(scopes) == 1
    assert len(harness.memory.load(scopes[0]).messages) == 4
    assert harness.workflow.inputs[0].selected_agents == ["progress"]
    assert harness.workflow.inputs[1].selected_agents == ["risk"]


@pytest.mark.e2e
def test_academic_data_unavailable_returns_safe_failed_response(monkeypatch):
    gateway = DeterministicAcademicGateway(fail_progress=True)
    workflow = ObservedWorkflow(create_academic_agent_workflow(gateway=gateway))
    service = ChatService(session_service=SessionService(), workflow=workflow)

    response = asyncio.run(service.process_message(ChatRequest(**payload(
        "How is student 123 progressing?"
    ))))

    assert "partially completed" in response.reply
    assert "could not be retrieved" in response.reply
    for forbidden in ("AgentState", "AgentResult", "traceback", "password", "MCPAcademic"):
        assert forbidden not in response.reply
