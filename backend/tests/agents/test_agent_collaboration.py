from __future__ import annotations

import asyncio
from typing import Any

from app.agents.state import AgentState, create_initial_state
from app.agents.types import AgentResult, WorkflowStatus
from app.agents.workflow import create_academic_agent_workflow
from app.gateways.policy_context import PolicyContextResult, PolicyEvidenceCandidate
from app.schemas.chat import ChatRequest
from app.schemas.memory import ConversationMemorySnapshot, MemoryMessage
from app.services.chat_service import ChatService
from app.services.conversation_memory import InMemoryConversationMemoryStore
from app.services.session_service import SessionService


FULL_ROUTE = [
    "progress",
    "study_rights",
    "risk",
    "recommendation",
    "reporting",
    "communication",
]


class CollaborationAcademicGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def get_student(self, student_id: int) -> dict[str, Any]:
        self.calls.append(("get_student", student_id))
        return {
            "success": True,
            "student": {"name": "Ada Student", "programme": "Computer Science"},
        }

    async def get_progress(self, student_id: int) -> dict[str, Any]:
        self.calls.append(("get_progress", student_id))
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

    async def get_study_right(self, student_id: int) -> dict[str, Any]:
        self.calls.append(("get_study_right", student_id))
        return {
            "success": True,
            "study_right": {
                "status": "EXPIRES_SOON",
                "extension_count": 1,
                "is_expiring_soon": True,
                "expiration_date": "2026-12-31",
            },
        }

    async def get_upcoming_events(self) -> dict[str, Any]:
        self.calls.append(("get_upcoming_events", 0))
        return {"success": True, "events": []}


class CollaborationPolicyGateway:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def retrieve_policy(self, query: str, *, top_k: int = 3):
        self.queries.append(query)
        return PolicyContextResult(
            query=query,
            candidates=(PolicyEvidenceCandidate(
                chunk_id=f"policy-{len(self.queries)}",
                text="Tutors should review verified risks and agree on next steps.",
                score=0.95,
                source="Tutor support policy",
                metadata={"source": "Tutor support policy"},
            ),),
        )


class ObservingWorkflow:
    def __init__(self, workflow) -> None:
        self.workflow = workflow
        self.initial_states: list[AgentState] = []
        self.final_states: list[AgentState] = []

    async def run(self, state: AgentState) -> AgentState:
        self.initial_states.append(state.model_copy(deep=True))
        result = await self.workflow.run(state)
        self.final_states.append(result.model_copy(deep=True))
        return result


def workflow(gateway=None, policies=None):
    return create_academic_agent_workflow(
        gateway=gateway or CollaborationAcademicGateway(),
        policy_gateway=policies or CollaborationPolicyGateway(),
    )


def run_workflow(state: AgentState, gateway=None, policies=None) -> AgentState:
    return asyncio.run(workflow(gateway, policies).run(state))


def collaboration_state(*, max_steps: int = 10) -> AgentState:
    memory = ConversationMemorySnapshot(
        conversation_id="83eb2d80-54ca-4ea8-b673-a85283cf0c06",
        student_id=1,
        messages=[MemoryMessage(
            role="user",
            content="Previously asked for a progress review.",
            interaction_status="completed",
            created_at="2026-08-04T10:00:00Z",
        )],
    )
    state = create_initial_state(
        request_id="collaboration-success",
        user_message=(
            "Review student STU-001's academic situation, determine whether "
            "progress or study rights require attention, recommend the next "
            "action, and prepare a tutor-facing response."
        ),
        student_id=1,
        conversation_id=str(memory.conversation_id),
        memory=memory,
        max_steps=max_steps,
    )
    state.selected_agents = list(FULL_ROUTE)
    return state


def test_real_six_agent_workflow_preserves_shared_context_and_results():
    gateway = CollaborationAcademicGateway()
    policies = CollaborationPolicyGateway()
    original = collaboration_state()

    result = run_workflow(original, gateway, policies)

    assert result.completed_agents == FULL_ROUTE
    assert result.pending_agents == []
    assert result.current_agent is None
    assert result.step_count == len(FULL_ROUTE)
    assert result.workflow_status is WorkflowStatus.PARTIAL
    assert list(result.agent_results) == FULL_ROUTE
    assert all(isinstance(item, AgentResult) for item in result.agent_results.values())
    assert {item.route for item in result.agent_results.values()} == set(FULL_ROUTE)
    assert result.student_id == 1
    assert result.request_id == "collaboration-success"
    assert result.memory == original.memory
    assert any("requires tutor attention" in warning for warning in result.warnings)

    risk = result.agent_results["risk"]
    assert {item["dimension"] for item in risk.data["risk_factors"]} == {
        "progress", "study_right",
    }
    recommendation = result.agent_results["recommendation"]
    assert {route for item in recommendation.data["recommendations"] for route in item["source_agents"]} >= {
        "progress", "study_rights", "risk",
    }
    report = result.agent_results["reporting"]
    assert report.data["performance"]["facts"]["completed_ects"] == 80
    assert report.data["study_right"]["facts"]["study_right_status"] == "EXPIRES_SOON"
    assert report.data["risks"]["risk_level"] == "MEDIUM"
    assert report.data["upcoming_actions"]["items"]
    communication = result.agent_results["communication"]
    assert result.final_response == communication.data["formatted_message"]
    assert "Recommended actions (advisory)" in result.final_response
    assert "policy-" not in result.final_response
    assert policies.queries == [
        "academic progress deficit tutor support policy",
        "expiring study right extension support policy",
    ]
    assert gateway.calls == [
        ("get_student", 1),
        ("get_progress", 1),
        ("get_student", 1),
        ("get_study_right", 1),
        ("get_student", 1),
        ("get_progress", 1),
        ("get_study_right", 1),
        ("get_upcoming_events", 0),
    ]


def test_separate_workflow_invocations_have_isolated_mutable_state():
    first = run_workflow(collaboration_state())
    second_state = collaboration_state()
    second_state.request_id = "collaboration-second"
    second = run_workflow(second_state)

    second.warnings.append("second-only warning")
    second.agent_results.pop("progress")

    assert "second-only warning" not in first.warnings
    assert "progress" in first.agent_results
    assert first.request_id != second.request_id


def test_max_steps_bounds_collaboration_without_duplicate_execution():
    result = run_workflow(collaboration_state(max_steps=3))

    assert result.completed_agents == FULL_ROUTE[:3]
    assert result.pending_agents == FULL_ROUTE[3:]
    assert result.step_count == 3
    assert set(result.agent_results) == set(FULL_ROUTE[:3])
    assert result.final_response is None
    assert result.workflow_status is WorkflowStatus.PARTIAL


def test_calendar_and_partial_collaborators_preserve_completed_results():
    state = create_initial_state(user_message="Analyse and format", student_id=1)
    state.selected_agents = ["progress", "calendar", "reporting", "communication"]

    result = run_workflow(state)

    assert result.completed_agents == ["progress", "calendar", "reporting", "communication"]
    assert result.pending_agents == []
    assert result.current_agent is None
    assert result.step_count == 4
    assert "progress" in result.agent_results
    assert result.agent_results["calendar"].status == "SUCCESS"
    assert "No registered agent for route 'calendar'." not in result.errors
    assert result.workflow_status is WorkflowStatus.PARTIAL
    assert any("study-right" in warning for warning in result.warnings)
    assert any("unavailable" in warning for warning in result.warnings)
    assert result.final_response is not None
    assert (
        "Do not treat missing information as confirmation that there is no risk."
        in result.final_response
    )
    assert "No registered agent" not in result.final_response


def test_chat_service_runs_real_collaboration_and_loads_prior_memory_next_time():
    gateway = CollaborationAcademicGateway()
    policies = CollaborationPolicyGateway()
    memory = InMemoryConversationMemoryStore()
    first_observer = ObservingWorkflow(workflow(gateway, policies))
    first_service = ChatService(
        session_service=SessionService(), workflow=first_observer, memory_store=memory
    )
    request = ChatRequest(
        message="Review student STU-001 and prepare the tutor response.",
        telegram_user_id=7001,
        telegram_chat_id=8002,
        student_id=1,
        selected_agents=FULL_ROUTE,
    )

    first_response = asyncio.run(
        first_service.process_message(request, trusted_telegram=True)
    )
    second_observer = ObservingWorkflow(workflow(gateway, policies))
    reconstructed_service = ChatService(
        session_service=SessionService(), workflow=second_observer, memory_store=memory
    )
    second_response = asyncio.run(
        reconstructed_service.process_message(request, trusted_telegram=True)
    )

    assert first_response.conversation_id == second_response.conversation_id
    assert first_response.reply.startswith("Tutor summary:")
    assert "Recommended actions (advisory)" in first_response.reply
    assert first_observer.final_states[0].completed_agents == FULL_ROUTE
    second_memory = second_observer.initial_states[0].memory
    assert second_memory is not None
    assert [(item.role, item.content) for item in second_memory.messages] == [
        ("user", request.message),
        ("assistant", first_response.reply),
    ]
    assert second_observer.initial_states[0].agent_results == {}
    assert second_observer.initial_states[0].telegram_user_id is None
    assert second_observer.initial_states[0].telegram_chat_id is None
    shared_state = second_observer.initial_states[0].model_dump(mode="json")
    assert "internal_service_key" not in shared_state
    assert "database_session" not in shared_state
    assert "telegram_conversation_mappings" not in shared_state
