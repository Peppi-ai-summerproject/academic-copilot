"""Unit tests for the Academic Tool Gateway — Issue #165."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from app.gateways.academic_tools import (
    AcademicToolGateway,
    AcademicToolGatewayError,
    MCPAcademicToolGateway,
)


def test_gateway_delegates_student_lookup() -> None:
    response = {"success": True, "student": {"id": 42}}
    student_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(student_tool=student_tool)

    result = asyncio.run(gateway.get_student(42))

    assert result is response
    student_tool.assert_called_once_with(42)


def test_gateway_delegates_progress_lookup() -> None:
    response = {"success": True, "progress": {"completed_ects": 120}}
    progress_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(progress_tool=progress_tool)

    result = asyncio.run(gateway.get_progress(7))

    assert result is response
    progress_tool.assert_called_once_with(7)


def test_gateway_delegates_study_right_lookup() -> None:
    response = {"success": False, "error": "STUDY_RIGHT_NOT_FOUND"}
    study_right_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(study_right_tool=study_right_tool)

    result = asyncio.run(gateway.get_study_right(9))

    assert result is response
    study_right_tool.assert_called_once_with(9)


def test_gateway_delegates_upcoming_events_lookup() -> None:
    response = {"success": True, "events": []}
    events_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(upcoming_events_tool=events_tool)

    result = asyncio.run(gateway.get_upcoming_events())

    assert result is response
    events_tool.assert_called_once_with()


def test_gateway_implements_protocol() -> None:
    assert isinstance(MCPAcademicToolGateway(), AcademicToolGateway)


def test_gateway_rejects_invalid_tool_response() -> None:
    gateway = MCPAcademicToolGateway(student_tool=Mock(return_value=None))

    with pytest.raises(AcademicToolGatewayError, match="get_student"):
        asyncio.run(gateway.get_student(1))


def test_gateway_delegates_discovery_tools_and_preserves_response() -> None:
    response = {"success": True, "courses": []}
    course_search_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(search_courses_tool=course_search_tool)

    result = asyncio.run(gateway.search_courses(query="software", limit=5))

    assert result is response
    course_search_tool.assert_called_once_with(query="software", limit=5)


def test_gateway_delegates_enrollment_tools() -> None:
    roster_tool = Mock(return_value={"success": True, "students": []})
    enrollments_tool = Mock(return_value={"success": True, "courses": []})
    enrollment_tool = Mock(return_value={"success": True, "enrollment": {"enrollment_id": 3}})
    gateway = MCPAcademicToolGateway(
        course_roster_tool=roster_tool,
        student_enrollments_tool=enrollments_tool,
        enrollment_tool=enrollment_tool,
    )

    asyncio.run(gateway.get_course_roster(course_id=2, enrollment_status="ENROLLED"))
    asyncio.run(gateway.get_student_enrollments(student_id=4))
    result = asyncio.run(gateway.get_enrollment(student_id=4, course_id=2))

    roster_tool.assert_called_once_with(course_id=2, enrollment_status="ENROLLED")
    enrollments_tool.assert_called_once_with(student_id=4)
    enrollment_tool.assert_called_once_with(student_id=4, course_id=2)
    assert result["enrollment"]["enrollment_id"] == 3


def test_gateway_delegates_teacher_assignment_tools() -> None:
    course_teachers_tool = Mock(return_value={"success": True, "teachers": []})
    teacher_courses_tool = Mock(return_value={"success": True, "assignments": []})
    gateway = MCPAcademicToolGateway(
        course_teachers_tool=course_teachers_tool,
        teacher_courses_tool=teacher_courses_tool,
    )

    course_result = asyncio.run(
        gateway.get_course_teachers(course_code="DIN24", role="LEAD_TEACHER")
    )
    teacher_result = asyncio.run(gateway.get_teacher_courses(teacher_id=8))

    assert course_result["teachers"] == []
    assert teacher_result["assignments"] == []
    course_teachers_tool.assert_called_once_with(
        course_code="DIN24",
        role="LEAD_TEACHER",
    )
    teacher_courses_tool.assert_called_once_with(teacher_id=8)


def test_gateway_delegates_student_group_tools() -> None:
    search = Mock(return_value={"success": True, "groups": []})
    lookup = Mock(return_value={"success": True, "group": {"id": 24}})
    students = Mock(return_value={"success": True, "students": []})
    courses = Mock(return_value={"success": True, "courses": []})
    gateway = MCPAcademicToolGateway(
        search_student_groups_tool=search,
        student_group_tool=lookup,
        student_group_students_tool=students,
        student_group_courses_tool=courses,
    )

    asyncio.run(gateway.search_student_groups(query="DIN24"))
    asyncio.run(gateway.get_student_group(24))
    asyncio.run(gateway.get_student_group_students(24))
    asyncio.run(gateway.get_student_group_courses(24))

    search.assert_called_once_with(query="DIN24")
    lookup.assert_called_once_with(24)
    students.assert_called_once_with(24)
    courses.assert_called_once_with(24)
