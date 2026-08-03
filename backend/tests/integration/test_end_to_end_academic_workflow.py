from __future__ import annotations

import asyncio
from typing import Any

from app.agents.progress_analysis_agent import ProgressAnalysisAgent
from app.agents.study_rights_agent import StudyRightsAgent
from app.agents.workflow import create_academic_agent_workflow, create_default_agent_registry
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService
from app.services.session_service import SessionService


class RecordingAcademicToolGateway:
    """Deterministic replacement for the production academic data boundary."""

    def __init__(
        self,
        *,
        student: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        study_right: dict[str, Any] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.student = student or {
            "success": True,
            "student": {"name": "Ada Student", "programme": "Computer Science"},
        }
        self.progress = progress or {
            "success": True,
            "progress": {
                "completed_ects": 120,
                "expected_ects": 120,
                "difference_ects": 0,
                "status": "ON_TRACK",
                "current_semester": 4,
                "progress_percentage": 100.0,
            },
        }
        self.study_right = study_right or {
            "success": True,
            "study_right": {
                "status": "ACTIVE",
                "extension_count": 0,
                "is_expiring_soon": False,
                "expiration_date": "2028-07-31",
            },
        }
        self.errors = errors or {}
        self.calls: list[tuple[str, int]] = []

    async def get_student(self, student_id: int) -> dict[str, Any]:
        return self._result("get_student", student_id, self.student)

    async def get_progress(self, student_id: int) -> dict[str, Any]:
        return self._result("get_progress", student_id, self.progress)

    async def get_study_right(self, student_id: int) -> dict[str, Any]:
        return self._result("get_study_right", student_id, self.study_right)

    def _result(
        self,
        operation: str,
        student_id: int,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((operation, student_id))
        if error := self.errors.get(operation):
            raise error
        return result


def make_service(
    gateway: RecordingAcademicToolGateway,
) -> tuple[ChatService, SessionService]:
    registry = create_default_agent_registry()
    assert registry.get("progress") is ProgressAnalysisAgent
    assert registry.get("study_rights") is StudyRightsAgent
    sessions = SessionService()
    workflow = create_academic_agent_workflow(registry=registry, gateway=gateway)
    return ChatService(session_service=sessions, workflow=workflow), sessions


def request(**changes: Any) -> ChatRequest:
    values: dict[str, Any] = {
        "message": "Review this student's academic situation",
        "telegram_user_id": 7001,
        "telegram_chat_id": 8002,
        "username": "tutor_teacher",
        "student_id": 42,
        "selected_agents": ["progress"],
    }
    values.update(changes)
    return ChatRequest(**values)


def process(service: ChatService, chat_request: ChatRequest) -> ChatResponse:
    return asyncio.run(service.process_message(chat_request))


def test_progress_request_runs_real_connected_path_and_passes_student_id():
    gateway = RecordingAcademicToolGateway()
    service, _ = make_service(gateway)

    response = process(service, request())

    assert isinstance(response, ChatResponse)
    assert response.reply == (
        "Academic analysis completed.\n\n"
        "- Ada Student (Computer Science) is on track with their studies. "
        "They have completed 120 ECTS, meeting the expected 120 ECTS milestone "
        "for semester 4 (100.0% of expected progress)."
    )
    assert gateway.calls == [("get_student", 42), ("get_progress", 42)]


def test_study_rights_request_runs_real_connected_path():
    gateway = RecordingAcademicToolGateway()
    service, _ = make_service(gateway)

    response = process(service, request(selected_agents=["study_rights"]))

    assert response.reply == (
        "Academic analysis completed.\n\n"
        "- Ada Student (Computer Science) has an active study right "
        "(expires 2028-07-31). No immediate action required."
    )
    assert gateway.calls == [("get_student", 42), ("get_study_right", 42)]


def test_multi_agent_response_and_gateway_calls_follow_selected_order():
    gateway = RecordingAcademicToolGateway()
    service, _ = make_service(gateway)

    response = process(
        service,
        request(selected_agents=["study_rights", "progress"]),
    )

    study_right_summary = "Ada Student (Computer Science) has an active study right"
    progress_summary = "Ada Student (Computer Science) is on track with their studies"
    assert response.reply.index(study_right_summary) < response.reply.index(progress_summary)
    assert gateway.calls == [
        ("get_student", 42),
        ("get_study_right", 42),
        ("get_student", 42),
        ("get_progress", 42),
    ]


def test_telegram_session_context_and_conversation_history_are_preserved():
    gateway = RecordingAcademicToolGateway()
    service, sessions = make_service(gateway)

    first = process(service, request(message="Check progress"))
    second = process(
        service,
        request(
            message="Now check the study right",
            telegram_chat_id=9003,
            username="updated_tutor",
            selected_agents=["study_rights"],
        ),
    )

    session = sessions.get_session(7001)
    assert session is not None
    assert session.telegram_user_id == 7001
    assert session.telegram_chat_id == 9003
    assert session.username == "updated_tutor"
    assert session.message_count == 2
    assert session.last_message == "Now check the study right"
    assert [(item.role, item.content) for item in session.history] == [
        ("user", "Check progress"),
        ("assistant", first.reply),
        ("user", "Now check the study right"),
        ("assistant", second.reply),
    ]


def test_unavailable_academic_data_produces_controlled_partial_response():
    gateway = RecordingAcademicToolGateway(
        progress={"success": False, "error": "PROGRESS_UNAVAILABLE"}
    )
    service, _ = make_service(gateway)

    response = process(service, request())

    assert response.reply == (
        "Academic analysis partially completed.\n\n"
        "- Ada Student is enrolled in Computer Science. Progress data could not "
        "be retrieved \u2014 curriculum data may be missing."
    )
    assert "PROGRESS_UNAVAILABLE" not in response.reply
    assert gateway.calls == [("get_student", 42), ("get_progress", 42)]


def test_missing_student_data_produces_controlled_failed_response():
    gateway = RecordingAcademicToolGateway(
        student={"success": False, "error": "STUDENT_NOT_FOUND"}
    )
    service, _ = make_service(gateway)

    response = process(service, request())

    assert response.reply == (
        "Academic analysis could not be completed.\n\n"
        "- Student with ID 42 was not found."
    )
    assert "STUDENT_NOT_FOUND" not in response.reply
    assert gateway.calls == [("get_student", 42)]


def test_unexpected_gateway_exception_returns_safe_final_chat_response():
    secret_details = "PostgreSQL password=secret at internal-db:5432"
    gateway = RecordingAcademicToolGateway(
        errors={"get_progress": RuntimeError(secret_details)}
    )
    service, sessions = make_service(gateway)

    response = process(service, request())

    assert isinstance(response, ChatResponse)
    assert response.reply == (
        "Academic analysis could not be completed.\n\n"
        "- Progress analysis could not be completed due to a system error."
    )
    assert secret_details not in response.reply
    assert "PostgreSQL" not in response.reply
    assert "internal-db" not in response.reply
    session = sessions.get_session(7001)
    assert session is not None
    assert session.history[-1].role == "assistant"
    assert session.history[-1].content == response.reply
    assert gateway.calls == [("get_student", 42), ("get_progress", 42)]
