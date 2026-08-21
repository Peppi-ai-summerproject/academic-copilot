from unittest.mock import Mock

import pytest

from app.repositories.academic_record_repository import AcademicRecordRepository


def _session_with_rows(*rows):
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = rows
    return session


def test_list_courses_for_student_returns_enrollment_state() -> None:
    session = _session_with_rows(
        {
            "id": 1,
            "course_code": "DII101",
            "course_name": "Digital Innovation Foundations",
            "credits": 5,
            "enrollment_status": "IN_PROGRESS",
            "enrolled_at": "2026-08-01",
        }
    )
    rows = AcademicRecordRepository(session).list_courses_for_student(7)
    assert rows[0]["enrollment_status"] == "IN_PROGRESS"
    statement, params = session.execute.call_args.args
    assert "course_enrollments" in statement.text
    assert params == {"student_id": 7}


def test_list_students_for_course_returns_roster_with_contact() -> None:
    session = _session_with_rows(
        {
            "id": 7,
            "student_number": "DEMO22101",
            "name": "Elina Demo",
            "email": "elina@example.invalid",
            "enrollment_status": "ENROLLED",
        }
    )
    rows = AcademicRecordRepository(session).list_students_for_course(1)
    assert rows[0]["student_number"] == "DEMO22101"
    assert rows[0]["email"] == "elina@example.invalid"


@pytest.mark.parametrize("status", ["ENROLLED", "IN_PROGRESS", "COMPLETED", "WITHDRAWN"])
def test_enrollment_lists_filter_canonical_status(status) -> None:
    session = _session_with_rows()
    repository = AcademicRecordRepository(session)

    repository.list_courses_for_student(7, enrollment_status=status)
    statement, params = session.execute.call_args.args
    assert "enrollment.enrollment_status = :enrollment_status" in statement.text
    assert params == {"student_id": 7, "enrollment_status": status}

    repository.list_students_for_course(1, enrollment_status=status)
    statement, params = session.execute.call_args.args
    assert "enrollment.enrollment_status = :enrollment_status" in statement.text
    assert params == {"course_id": 1, "enrollment_status": status}


def test_get_enrollment_returns_joined_record_or_none() -> None:
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "enrollment_id": 9,
        "student_id": 7,
        "course_id": 1,
        "enrollment_status": "ENROLLED",
    }

    row = AcademicRecordRepository(session).get_enrollment(7, 1)

    assert row == {
        "enrollment_id": 9,
        "student_id": 7,
        "course_id": 1,
        "enrollment_status": "ENROLLED",
    }
    statement, params = session.execute.call_args.args
    assert "course_enrollments" in statement.text
    assert params == {"student_id": 7, "course_id": 1}


@pytest.mark.parametrize("status", ["PASSED", "FAILED"])
def test_results_for_student_can_filter_canonical_result_status(status) -> None:
    session = _session_with_rows()
    rows = AcademicRecordRepository(session).list_results_for_student(
        7,
        result_status=status,
    )
    assert rows == []
    statement, params = session.execute.call_args.args
    assert "course_completions" in statement.text
    assert "completion.result_status = :result_status" in statement.text
    assert params == {"entity_id": 7, "result_status": status}


def test_results_for_course_supports_pass_fail_counts_without_reimplementing_policy() -> None:
    session = _session_with_rows(
        {"student_id": 7, "course_code": "DII101", "result_status": "PASSED"},
        {"student_id": 8, "course_code": "DII101", "result_status": "FAILED"},
    )
    rows = AcademicRecordRepository(session).list_results_for_course(1)
    assert [row["result_status"] for row in rows] == ["PASSED", "FAILED"]
    statement, params = session.execute.call_args.args
    assert "completion.course_id = :entity_id" in statement.text
    assert "student.name AS student_name" in statement.text
    assert "INNER JOIN students AS student" in statement.text
    assert params == {"entity_id": 1}
