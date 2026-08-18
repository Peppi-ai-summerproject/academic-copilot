from unittest.mock import Mock

from app.repositories.course_repository import CourseRepository


def _session_with_rows(*rows):
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = rows
    return session


def test_get_course_by_human_facing_code_is_case_insensitive() -> None:
    row = {
        "id": 4,
        "course_code": "DIN24",
        "course_name": "Digital Innovation Foundations",
        "credits": 5,
        "programme_code": "DIN2024S",
        "semester": 1,
        "is_active": True,
    }
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = row

    assert CourseRepository(session).get_by_code("din24") == row
    statement, params = session.execute.call_args.args
    assert "LOWER(course_code) = LOWER(:course_code)" in statement.text
    assert params == {"course_code": "din24"}


def test_get_course_by_code_returns_none_for_missing_course() -> None:
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    assert CourseRepository(session).get_by_code("UNKNOWN") is None


def test_course_search_supports_code_or_name_and_empty_results() -> None:
    session = _session_with_rows()
    assert CourseRepository(session).search("innovation") == []
    statement, params = session.execute.call_args.args
    assert "LOWER(course_code) LIKE :query" in statement.text
    assert "LOWER(course_name) LIKE :query" in statement.text
    assert params == {"query": "%innovation%"}


def test_list_all_courses_uses_stable_course_code_order() -> None:
    session = _session_with_rows({"id": 1, "course_code": "DIN24"})
    courses = CourseRepository(session).search()
    assert courses == [{"id": 1, "course_code": "DIN24"}]
    statement, params = session.execute.call_args.args
    assert "ORDER BY course_code ASC, id ASC" in statement.text
    assert params == {}


def test_list_teachers_returns_contact_and_assignment_role() -> None:
    session = _session_with_rows(
        {
            "id": 8,
            "display_name": "Anna Example",
            "email": "anna@example.invalid",
            "assignment_role": "LEAD_TEACHER",
        }
    )
    teachers = CourseRepository(session).list_teachers(4)
    assert teachers[0]["email"] == "anna@example.invalid"
    statement, params = session.execute.call_args.args
    assert "teacher_course_assignments" in statement.text
    assert params == {"course_id": 4}


def test_list_teachers_filters_exact_role_and_uses_stable_order() -> None:
    session = _session_with_rows()
    CourseRepository(session).list_teachers(4, assignment_role="LEAD_TEACHER")
    statement, params = session.execute.call_args.args
    assert "assignment.assignment_role = :assignment_role" in statement.text
    assert "ORDER BY assignment.assignment_role ASC" in statement.text
    assert params == {"course_id": 4, "assignment_role": "LEAD_TEACHER"}
