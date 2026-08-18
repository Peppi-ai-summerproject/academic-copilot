from unittest.mock import Mock

import pytest

from app.services.teacher_assignment_service import TeacherAssignmentService


@pytest.fixture
def dependencies():
    teachers = Mock()
    courses = Mock()
    teachers.get_by_id.return_value = {
        "id": 8,
        "display_name": "Anna Example",
        "email": "anna@example.invalid",
        "is_active": True,
    }
    courses.get_by_id.return_value = {
        "id": 4,
        "course_code": "DIN24",
        "course_name": "Digital Innovation Foundations",
    }
    courses.get_by_code.return_value = courses.get_by_id.return_value
    courses.list_teachers.return_value = []
    teachers.list_courses_for_teacher.return_value = []
    return teachers, courses


def test_course_with_no_assignments_is_successful_empty_result(dependencies) -> None:
    teachers, courses = dependencies
    result = TeacherAssignmentService(teachers, courses).get_course_teachers(
        course_code="din24"
    )
    assert result["success"] is True
    assert result["teacher_count"] == 0
    assert result["teachers"] == []
    courses.get_by_code.assert_called_once_with("din24")


def test_course_returns_multiple_teachers_without_collapsing_roles(dependencies) -> None:
    teachers, courses = dependencies
    courses.list_teachers.return_value = [
        {"id": 8, "assignment_role": "LEAD_TEACHER"},
        {"id": 9, "assignment_role": "TEACHER"},
    ]
    result = TeacherAssignmentService(teachers, courses).get_course_teachers(
        course_id=4
    )
    assert result["teacher_count"] == 2
    assert [row["id"] for row in result["teachers"]] == [8, 9]


def test_multiple_lead_teachers_are_all_returned(dependencies) -> None:
    teachers, courses = dependencies
    courses.list_teachers.return_value = [
        {"id": 8, "assignment_role": "LEAD_TEACHER"},
        {"id": 9, "assignment_role": "LEAD_TEACHER"},
    ]
    result = TeacherAssignmentService(teachers, courses).get_course_teachers(
        course_id=4,
        role=" lead_teacher ",
    )
    assert result["teacher_count"] == 2
    assert result["filter"] == {"role": "LEAD_TEACHER"}
    courses.list_teachers.assert_called_once_with(
        4,
        assignment_role="LEAD_TEACHER",
    )


def test_teacher_with_multiple_courses_and_nullable_contact(dependencies) -> None:
    teachers, courses = dependencies
    teachers.get_by_id.return_value["email"] = None
    teachers.list_courses_for_teacher.return_value = [
        {"id": 1, "course_code": "DBS24", "assignment_role": "TEACHER"},
        {"id": 4, "course_code": "DIN24", "assignment_role": "LEAD_TEACHER"},
    ]
    result = TeacherAssignmentService(teachers, courses).get_teacher_courses(8)
    assert result["success"] is True
    assert result["teacher"]["email"] is None
    assert result["assignment_count"] == 2


def test_teacher_with_no_courses_is_successful_empty_result(dependencies) -> None:
    teachers, courses = dependencies
    result = TeacherAssignmentService(teachers, courses).get_teacher_courses(8)
    assert result["success"] is True
    assert result["assignment_count"] == 0
    assert result["assignments"] == []


@pytest.mark.parametrize("role", ["", "   ", 7, False])
def test_invalid_role_filter_is_rejected(role, dependencies) -> None:
    teachers, courses = dependencies
    result = TeacherAssignmentService(teachers, courses).get_teacher_courses(8, role)
    assert result["error"] == "INVALID_ROLE_FILTER"
    teachers.get_by_id.assert_not_called()


def test_missing_course_is_distinct_from_empty_assignments(dependencies) -> None:
    teachers, courses = dependencies
    courses.get_by_id.return_value = None
    result = TeacherAssignmentService(teachers, courses).get_course_teachers(
        course_id=99
    )
    assert result["error"] == "COURSE_NOT_FOUND"
    courses.list_teachers.assert_not_called()


def test_missing_teacher_is_distinct_from_empty_assignments(dependencies) -> None:
    teachers, courses = dependencies
    teachers.get_by_id.return_value = None
    result = TeacherAssignmentService(teachers, courses).get_teacher_courses(99)
    assert result["error"] == "TEACHER_NOT_FOUND"
    teachers.list_courses_for_teacher.assert_not_called()


@pytest.mark.parametrize("teacher_id", [0, -1, True, "8", None])
def test_invalid_teacher_id_is_rejected(teacher_id, dependencies) -> None:
    teachers, courses = dependencies
    result = TeacherAssignmentService(teachers, courses).get_teacher_courses(
        teacher_id
    )
    assert result["error"] == "INVALID_TEACHER_ID"


def test_course_identifier_requires_exactly_one_supported_identifier(dependencies) -> None:
    teachers, courses = dependencies
    service = TeacherAssignmentService(teachers, courses)
    assert service.get_course_teachers()["error"] == "INVALID_COURSE_IDENTIFIER"
    assert service.get_course_teachers(course_id=4, course_code="DIN24")["error"] == "INVALID_COURSE_IDENTIFIER"


def test_search_contract_identifiers_compose_with_assignment_contract(dependencies) -> None:
    teachers, courses = dependencies
    service = TeacherAssignmentService(teachers, courses)
    teacher_search_row = {"id": 8, "display_name": "Anna Example"}
    course_search_row = {"id": 4, "course_code": "DIN24"}
    assert service.get_teacher_courses(teacher_search_row["id"])["success"] is True
    assert service.get_course_teachers(course_id=course_search_row["id"])["success"] is True
