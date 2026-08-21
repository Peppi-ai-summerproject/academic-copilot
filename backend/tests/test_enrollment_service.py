from unittest.mock import Mock

import pytest

from app.services.enrollment_service import EnrollmentService


@pytest.fixture
def dependencies():
    records = Mock()
    students = Mock()
    courses = Mock()
    students.get_by_id.return_value = {"id": 7, "student_number": "S007"}
    courses.get_by_id.return_value = {"id": 1, "course_code": "DII101"}
    records.list_students_for_course.return_value = []
    records.list_courses_for_student.return_value = []
    return records, students, courses


def test_course_roster_preserves_valid_empty_result(dependencies) -> None:
    records, students, courses = dependencies
    result = EnrollmentService(records, students, courses).get_course_roster(1)
    assert result == {
        "success": True,
        "course": {"id": 1, "course_code": "DII101"},
        "filter": {"enrollment_status": None},
        "student_count": 0,
        "students": [],
    }


def test_student_enrollments_normalizes_and_filters_status(dependencies) -> None:
    records, students, courses = dependencies
    records.list_courses_for_student.return_value = [{"id": 1}]
    result = EnrollmentService(records, students, courses).get_student_enrollments(7, " in_progress ")
    assert result["success"] is True
    assert result["course_count"] == 1
    assert result["filter"] == {"enrollment_status": "IN_PROGRESS"}
    records.list_courses_for_student.assert_called_once_with(7, enrollment_status="IN_PROGRESS")


@pytest.mark.parametrize("value", [0, -1, True, "1", None])
def test_course_roster_rejects_invalid_ids(value, dependencies) -> None:
    records, students, courses = dependencies
    result = EnrollmentService(records, students, courses).get_course_roster(value)
    assert result["error"] == "INVALID_COURSE_ID"


@pytest.mark.parametrize("value", [0, -1, True, "7", None])
def test_student_enrollments_rejects_invalid_ids(value, dependencies) -> None:
    records, students, courses = dependencies
    result = EnrollmentService(records, students, courses).get_student_enrollments(value)
    assert result["error"] == "INVALID_STUDENT_ID"


@pytest.mark.parametrize("value", ["ACTIVE", "", 3])
def test_lists_reject_invalid_enrollment_status(value, dependencies) -> None:
    records, students, courses = dependencies
    result = EnrollmentService(records, students, courses).get_course_roster(1, value)
    assert result["error"] == "INVALID_ENROLLMENT_STATUS"
    courses.get_by_id.assert_not_called()


def test_missing_entities_are_distinct_from_empty_lists(dependencies) -> None:
    records, students, courses = dependencies
    courses.get_by_id.return_value = None
    assert EnrollmentService(records, students, courses).get_course_roster(99)["error"] == "COURSE_NOT_FOUND"
    students.get_by_id.return_value = None
    assert EnrollmentService(records, students, courses).get_student_enrollments(99)["error"] == "STUDENT_NOT_FOUND"


def test_individual_enrollment_distinguishes_missing_relation(dependencies) -> None:
    records, students, courses = dependencies
    records.get_enrollment.return_value = None
    service = EnrollmentService(records, students, courses)
    assert service.get_enrollment(7, 1)["error"] == "ENROLLMENT_NOT_FOUND"
    records.get_enrollment.return_value = {"enrollment_id": 3, "student_id": 7, "course_id": 1}
    assert service.get_enrollment(7, 1) == {
        "success": True,
        "enrollment": {"enrollment_id": 3, "student_id": 7, "course_id": 1},
    }


def test_individual_enrollment_checks_student_then_course(dependencies) -> None:
    records, students, courses = dependencies
    students.get_by_id.return_value = None
    service = EnrollmentService(records, students, courses)
    assert service.get_enrollment(7, 1)["error"] == "STUDENT_NOT_FOUND"
    courses.get_by_id.assert_not_called()

    students.get_by_id.return_value = {"id": 7}
    courses.get_by_id.return_value = None
    assert service.get_enrollment(7, 1)["error"] == "COURSE_NOT_FOUND"
