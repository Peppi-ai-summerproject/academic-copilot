from unittest.mock import Mock

from app.repositories.student_group_repository import StudentGroupRepository


def _session_with_rows(*rows):
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = rows
    return session


def test_group_lookup_returns_programme_relationship_by_canonical_code() -> None:
    row = {
        "id": 24,
        "group_code": "DIN24",
        "group_name": "Digital Innovation 2024 cohort",
        "programme_id": 3,
        "programme_code": "DIN2024S",
        "programme_name": "Business IT",
        "is_active": True,
    }
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = row

    result = StudentGroupRepository(session).get_by_code(" din24 ")

    assert result == row
    statement, params = session.execute.call_args.args
    assert "FROM student_groups" in statement.text
    assert "INNER JOIN degree_programmes" in statement.text
    assert params == {"group_code": "din24"}


def test_group_lists_students_through_canonical_group_id() -> None:
    session = _session_with_rows(
        {"id": 1, "student_number": "DEMO22101", "name": "Elina Demo"},
        {"id": 2, "student_number": "DEMO22102", "name": "Oskari Example"},
    )

    students = StudentGroupRepository(session).list_students(24)

    assert len(students) == 2
    statement, params = session.execute.call_args.args
    assert "WHERE group_id = :group_id" in statement.text
    assert params == {"group_id": 24}


def test_group_lists_multiple_independent_courses() -> None:
    session = _session_with_rows(
        {"id": 10, "course_code": "DII101", "course_name": "Digital Innovation Foundations"},
        {"id": 11, "course_code": "DBS24", "course_name": "Database Systems"},
    )

    courses = StudentGroupRepository(session).list_courses(24)

    assert [course["course_code"] for course in courses] == ["DII101", "DBS24"]
    statement, params = session.execute.call_args.args
    assert "FROM student_group_courses" in statement.text
    assert "INNER JOIN courses" in statement.text
    assert params == {"group_id": 24}


def test_group_lookup_by_id_and_search_return_canonical_rows() -> None:
    row = {"id": 24, "group_code": "DIN24", "group_name": "Digital Innovation"}
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = row
    repository = StudentGroupRepository(session)

    assert repository.get_by_id(24) == row
    assert session.execute.call_args.args[1] == {"group_id": 24}

    session.execute.return_value.mappings.return_value.all.return_value = [row]
    assert repository.search(" din ") == [row]
    assert session.execute.call_args.args[1] == {"query": "%din%"}
