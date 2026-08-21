import asyncio
import pytest
from app.agents.state import AgentState
from app.agents.workflow import create_default_agent_registry
from app.schemas.chat import ChatRequest
from app.services.academic_entity_resolver import ResolvedAcademicEntity
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.agents.types import WorkflowStatus


class RecordingWorkflow:
    def __init__(self): self.states = []
    async def run(self, state: AgentState):
        self.states.append(state.model_copy(deep=True))
        state.workflow_status = WorkflowStatus.COMPLETED
        state.final_response = "done"
        return state


class Resolver:
    def __init__(self, resolutions): self.resolutions = resolutions
    async def resolve(self, entity_type, text): return self.resolutions[(entity_type, text)]


def _request(message):
    return ChatRequest(message=message, telegram_user_id=1, telegram_chat_id=2)


def _service(workflow, resolver):
    registry = create_default_agent_registry()
    return ChatService(session_service=SessionService(), workflow=workflow, registry=registry, entity_resolver=resolver)


def test_chat_resolves_multi_entity_query_before_routing_to_data_agent():
    workflow = RecordingWorkflow()
    resolver = Resolver({
        ("STUDENT", "Anna Korhonen"): ResolvedAcademicEntity("STUDENT", "Anna Korhonen", "RESOLVED", 7, "Anna Korhonen"),
        ("COURSE", "DII101"): ResolvedAcademicEntity("COURSE", "DII101", "RESOLVED", 4, "Digital Innovation Foundations", ({"course_id": 4, "course_code": "DII101"},)),
    })
    response = asyncio.run(_service(workflow, resolver).process_message(_request("Did Anna Korhonen pass DII101?")))
    assert response.reply == "done"
    state = workflow.states[0]
    assert state.intent == "academic_data"
    assert state.selected_agents == ["academic_data"]
    assert state.parameters["capability"] == "student_course_result"
    assert [row["canonical_id"] for row in state.resolved_entities] == [7, 4]


def test_ambiguous_entity_returns_clarification_without_workflow():
    workflow = RecordingWorkflow()
    ambiguous = ResolvedAcademicEntity(
        "STUDENT", "Anna", "AMBIGUOUS", candidates=(
            {"student_number": "S1", "name": "Anna One"},
            {"student_number": "S2", "name": "Anna Two"},
        )
    )
    response = asyncio.run(_service(workflow, Resolver({("STUDENT", "Anna"): ambiguous})).process_message(_request("Find Anna.")))
    assert workflow.states == []
    assert "multiple" in response.reply.lower()
    assert "S1" in response.reply and "S2" in response.reply


def test_missing_entity_returns_not_found_without_workflow():
    workflow = RecordingWorkflow()
    missing = ResolvedAcademicEntity("COURSE", "DIN99", "NOT_FOUND")
    response = asyncio.run(_service(workflow, Resolver({("COURSE", "DIN99"): missing})).process_message(_request("What is DIN99?")))
    assert workflow.states == []
    assert "could not find" in response.reply.lower()


@pytest.mark.parametrize(
    ("message", "entity_type", "reference", "candidates"),
    [
        ("What is DII101?", "COURSE", "DII101", ({"course_code": "DII101-A"}, {"course_code": "DII101-B"})),
        ("Find teacher Matti Virtanen.", "TEACHER", "Matti Virtanen", ({"name": "Matti A"}, {"name": "Matti B"})),
    ],
)
def test_ambiguous_course_and_teacher_never_execute_workflow(message, entity_type, reference, candidates):
    workflow = RecordingWorkflow()
    ambiguous = ResolvedAcademicEntity(entity_type, reference, "AMBIGUOUS", candidates=candidates)
    response = asyncio.run(_service(workflow, Resolver({(entity_type, reference): ambiguous})).process_message(_request(message)))
    assert workflow.states == []
    assert "which one" in response.reply.lower()
