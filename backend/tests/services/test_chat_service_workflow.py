from __future__ import annotations

import asyncio

import pytest

from app.agents.registry import AgentRegistry
from app.agents.state import AgentState
from app.agents.types import AgentResult, WorkflowStatus
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.session_service import SessionService


class FakeWorkflow:
    def __init__(
        self,
        *,
        status: WorkflowStatus = WorkflowStatus.COMPLETED,
        results: dict[str, AgentResult] | None = None,
        error: Exception | None = None,
        final_response: str | None = None,
    ) -> None:
        self.status = status
        self.results = results or {}
        self.error = error
        self.final_response = final_response
        self.states: list[AgentState] = []

    async def run(self, state: AgentState) -> AgentState:
        self.states.append(state.model_copy(deep=True))
        if self.error is not None:
            raise self.error
        state.workflow_status = self.status
        state.agent_results = self.results
        state.final_response = self.final_response
        return state


class RegisteredAgent:
    pass


def result(route: str, summary: str, status: str = "SUCCESS") -> AgentResult:
    return AgentResult(
        agent_name=f"{route.title()}Agent",
        route=route,
        status=status,
        summary=summary,
    )


def request(**changes) -> ChatRequest:
    values = {
        "message": "Check this student",
        "telegram_user_id": 101,
        "telegram_chat_id": 202,
        "username": "tutor",
    }
    values.update(changes)
    return ChatRequest(**values)


def process(service: ChatService, chat_request: ChatRequest):
    return asyncio.run(service.process_message(chat_request))


def registry(*routes: str) -> AgentRegistry:
    result = AgentRegistry()
    for route in routes:
        result.register(route, RegisteredAgent)  # type: ignore[arg-type]
    return result


def make_service(
    workflow: FakeWorkflow,
    *,
    agent_registry: AgentRegistry | None = None,
) -> tuple[ChatService, SessionService]:
    sessions = SessionService()
    return ChatService(
        session_service=sessions,
        workflow=workflow,
        registry=agent_registry,
    ), sessions


def test_ambiguous_request_returns_controlled_fallback_and_preserves_session_history():
    workflow = FakeWorkflow()
    service, sessions = make_service(workflow)

    response = process(service, request())

    assert response.reply == "Please clarify which academic information you want me to check."
    assert workflow.states == []
    session = sessions.get_session(101)
    assert session is not None
    assert [message.role for message in session.history] == ["user", "assistant"]


def test_natural_language_progress_request_routes_automatically() -> None:
    workflow = FakeWorkflow(results={"progress": result("progress", "On track")})
    service, sessions = make_service(workflow, agent_registry=registry("progress"))

    response = process(
        service,
        request(message="How is student 123 progressing?", student_id=123),
    )

    assert workflow.states[0].intent == "progress"
    assert workflow.states[0].selected_agents == ["progress"]
    assert response.reply == "Academic analysis completed.\n\n- On track"
    assert sessions.get_session(101).message_count == 1


def test_natural_language_risk_request_preserves_current_single_route_plan() -> None:
    workflow = FakeWorkflow(results={"risk": result("risk", "Medium risk")})
    service, _ = make_service(workflow, agent_registry=registry("risk"))

    process(service, request(message="Is student 123 at risk?", student_id=123))

    assert workflow.states[0].intent == "risk"
    assert workflow.states[0].selected_agents == ["risk"]


def test_natural_language_recommendation_request_uses_dependency_order() -> None:
    workflow = FakeWorkflow()
    service, _ = make_service(
        workflow,
        agent_registry=registry("risk", "recommendation"),
    )

    process(
        service,
        request(message="What should I do to help this student?", student_id=123),
    )

    assert workflow.states[0].intent == "recommendation"
    assert workflow.states[0].selected_agents == ["risk", "recommendation"]


def test_natural_language_reporting_request_preserves_full_dependency_order() -> None:
    workflow = FakeWorkflow()
    routes = ("progress", "study_rights", "risk", "recommendation", "reporting")
    service, _ = make_service(workflow, agent_registry=registry(*routes))

    process(
        service,
        request(message="Give me an academic summary of student 123.", student_id=123),
    )

    assert workflow.states[0].intent == "reporting"
    assert workflow.states[0].selected_agents == list(routes)


def test_explicit_routes_override_detected_intent_without_dependency_expansion() -> None:
    workflow = FakeWorkflow()
    service, _ = make_service(
        workflow,
        agent_registry=registry("progress", "risk"),
    )

    process(
        service,
        request(message="Is student 123 at risk?", selected_agents=["progress"]),
    )

    assert workflow.states[0].intent is None
    assert workflow.states[0].selected_agents == ["progress"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Hi", "No academic analysis was requested."),
        (
            "What is the weather tomorrow?",
            "I could not match that request to a supported academic analysis.",
        ),
        (
            "Check this student.",
            "Please clarify which academic information you want me to check.",
        ),
    ],
)
def test_non_routable_messages_do_not_execute_workflow(
    message: str,
    expected: str,
) -> None:
    workflow = FakeWorkflow()
    service, _ = make_service(workflow)

    response = process(service, request(message=message))

    assert response.reply == expected
    assert workflow.states == []


def test_selection_failure_does_not_execute_invalid_plan() -> None:
    workflow = FakeWorkflow()
    service, _ = make_service(workflow, agent_registry=registry())

    response = process(
        service,
        request(message="Is student 123 at risk?", student_id=123),
    )

    assert response.reply.startswith("I could not route this academic request safely")
    assert workflow.states == []


def test_workflow_request_maps_chat_context_to_initial_state():
    workflow = FakeWorkflow(results={"progress": result("progress", "On track")})
    service, _ = make_service(workflow)

    process(
        service,
        request(student_id=42, selected_agents=["progress"]),
    )

    state = workflow.states[0]
    assert state.user_message == "Check this student"
    assert state.student_id == 42
    assert state.telegram_user_id == 101
    assert state.telegram_chat_id == 202
    assert state.selected_agents == ["progress"]
    assert state.workflow_status is WorkflowStatus.PENDING


def test_completed_single_agent_workflow_formats_summary():
    workflow = FakeWorkflow(results={"progress": result("progress", "On track")})
    service, _ = make_service(workflow)

    response = process(service, request(selected_agents=["progress"]))

    assert response.reply == "Academic analysis completed.\n\n- On track"


def test_workflow_final_response_is_returned_for_existing_telegram_flow():
    workflow = FakeWorkflow(final_response="Tutor-ready Telegram response")
    service, sessions = make_service(workflow)

    response = process(service, request(selected_agents=["communication"]))

    assert response.reply == "Tutor-ready Telegram response"
    assert sessions.get_session(101).history[-1].content == response.reply


def test_multi_agent_summaries_follow_selected_agent_order():
    workflow = FakeWorkflow(
        results={
            "progress": result("progress", "Progress summary"),
            "study_rights": result("study_rights", "Study-right summary"),
        }
    )
    service, _ = make_service(workflow)

    response = process(
        service,
        request(selected_agents=["study_rights", "progress"]),
    )

    assert response.reply.endswith("- Study-right summary\n- Progress summary")


def test_partial_workflow_has_partial_status_and_available_summary():
    workflow = FakeWorkflow(
        status=WorkflowStatus.PARTIAL,
        results={"progress": result("progress", "Some data", "PARTIAL")},
    )
    service, _ = make_service(workflow)

    response = process(service, request(selected_agents=["progress"]))

    assert response.reply == "Academic analysis partially completed.\n\n- Some data"


def test_failed_workflow_formats_controlled_response():
    workflow = FakeWorkflow(status=WorkflowStatus.FAILED)
    service, _ = make_service(workflow)

    response = process(service, request(selected_agents=["progress"]))

    assert response.reply == (
        "Academic analysis could not be completed.\n\n"
        "No academic result is available."
    )


def test_completed_workflow_with_empty_results_is_safe():
    service, _ = make_service(FakeWorkflow())

    response = process(service, request(selected_agents=["progress"]))

    assert "completed without a result summary" in response.reply


def test_workflow_exception_is_controlled_and_assistant_reply_is_stored():
    service, sessions = make_service(FakeWorkflow(error=RuntimeError("boom")))

    response = process(service, request(selected_agents=["progress"]))

    assert response.reply == (
        "I could not complete the academic analysis. Please try again."
    )
    session = sessions.get_session(101)
    assert session is not None
    assert session.history[-1].role == "assistant"
    assert session.history[-1].content == response.reply


def test_user_and_assistant_messages_update_existing_session():
    workflow = FakeWorkflow(results={"progress": result("progress", "On track")})
    service, sessions = make_service(workflow)

    process(service, request(selected_agents=["progress"]))
    process(service, request(message="Again", selected_agents=["progress"]))

    session = sessions.get_session(101)
    assert session is not None
    assert session.message_count == 2
    assert [message.role for message in session.history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
