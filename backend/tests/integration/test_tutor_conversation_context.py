from __future__ import annotations

import asyncio

from app.agents.state import AgentState
from app.agents.types import WorkflowStatus
from app.agents.workflow import create_default_agent_registry
from app.schemas.chat import ChatRequest
from app.services.academic_entity_resolver import ResolvedAcademicEntity
from app.services.chat_service import ChatService
from app.services.conversation_memory import InMemoryConversationMemoryStore
from app.services.session_service import SessionService


class RecordingWorkflow:
    def __init__(self):
        self.states: list[AgentState] = []

    async def run(self, state: AgentState) -> AgentState:
        self.states.append(state.model_copy(deep=True))
        state.workflow_status = WorkflowStatus.COMPLETED
        state.final_response = "done"
        return state


class Resolver:
    async def resolve(self, kind, text):
        rows = {
            ("STUDENT", "Anna Korhonen"): (7, "Anna Korhonen", [{"student_number": "S7"}]),
            ("STUDENT", "John Smith"): (8, "John Smith", [{"student_number": "S8"}]),
            ("COURSE", "DIN24"): (24, "Digital Innovation", [{"course_code": "DIN24"}]),
            ("COURSE", "MAT101"): (101, "Mathematics", [{"course_code": "MAT101"}]),
            ("TEACHER", "Matti Virtanen"): (31, "Matti Virtanen", []),
        }
        value = rows.get((kind, text))
        if value is None:
            return ResolvedAcademicEntity(kind, text, "NOT_FOUND")
        identifier, name, candidates = value
        return ResolvedAcademicEntity(kind, text, "RESOLVED", identifier, name, tuple(candidates))


def harness():
    workflow = RecordingWorkflow()
    service = ChatService(
        session_service=SessionService(),
        workflow=workflow,
        memory_store=InMemoryConversationMemoryStore(),
        registry=create_default_agent_registry(),
        entity_resolver=Resolver(),
    )
    return service, workflow


def send(service, message, *, user=1, chat=2):
    request = ChatRequest(message=message, telegram_user_id=user, telegram_chat_id=chat)
    return asyncio.run(service.process_message(request, trusted_telegram=True))


def entity_ids(state):
    return {row["entity_type"]: row["canonical_id"] for row in state.resolved_entities}


def test_student_context_reaches_specialized_and_data_routes_across_turns():
    service, workflow = harness()
    for message in (
        "Show me Anna Korhonen.",
        "How is she progressing?",
        "Which courses is she taking?",
        "Is she at risk?",
    ):
        assert send(service, message).reply == "done"

    assert [state.selected_agents for state in workflow.states] == [
        ["academic_data"], ["progress"], ["academic_data"], ["risk"],
    ]
    assert [state.student_id for state in workflow.states] == [7, 7, 7, 7]


def test_course_context_is_reused_and_explicit_course_wins():
    service, workflow = harness()
    for message in (
        "Show me DIN24.", "Who teaches it?", "Who is enrolled?", "Who failed?",
        "Who failed MAT101?", "What is the pass rate?",
    ):
        send(service, message)

    assert [entity_ids(state)["COURSE"] for state in workflow.states] == [24, 24, 24, 24, 101, 101]
    assert [state.parameters.get("capability") for state in workflow.states] == [
        "course_lookup", "course_teachers", "course_roster", "course_results",
        "course_results", "course_analytics",
    ]


def test_teacher_context_is_reused_for_pronoun_followups():
    service, workflow = harness()
    for message in ("Find Matti Virtanen.", "What is his email?", "Which courses does he teach?"):
        send(service, message)

    assert [entity_ids(state)["TEACHER"] for state in workflow.states] == [31, 31, 31]
    assert [state.parameters["capability"] for state in workflow.states] == [
        "teacher_lookup", "teacher_contact", "teacher_courses",
    ]


def test_student_and_course_coexist_and_course_switch_preserves_student():
    service, workflow = harness()
    for message in ("Show me Anna Korhonen.", "Did she pass DIN24?", "What grade did she get?", "What about MAT101?"):
        send(service, message)

    assert entity_ids(workflow.states[1]) == {"STUDENT": 7, "COURSE": 24}
    assert entity_ids(workflow.states[2]) == {"STUDENT": 7, "COURSE": 24}
    assert entity_ids(workflow.states[3]) == {"STUDENT": 7, "COURSE": 101}


def test_student_switching_updates_student_and_preserves_course():
    service, workflow = harness()
    for message in ("Show me DIN24.", "Show me Anna Korhonen.", "Now show John Smith.", "How is he progressing?"):
        send(service, message)

    assert entity_ids(workflow.states[2]) == {"STUDENT": 8, "COURSE": 24}
    assert workflow.states[3].student_id == 8


def test_missing_context_clarifies_and_sessions_are_isolated():
    service, workflow = harness()
    send(service, "Show me Anna Korhonen.", user=1, chat=10)
    response = send(service, "Which courses is she taking?", user=1, chat=11)

    assert "Which student" in response.reply
    assert len(workflow.states) == 1


def test_failed_resolution_does_not_replace_previous_course():
    service, workflow = harness()
    send(service, "Show me DIN24.")
    response = send(service, "Show me XYZ999.")
    send(service, "What is the pass rate?")

    assert "could not find" in response.reply
    assert [entity_ids(state)["COURSE"] for state in workflow.states] == [24, 24]
