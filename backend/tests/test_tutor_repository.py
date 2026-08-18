from unittest.mock import Mock

from app.repositories.tutor_repository import TutorRepository


def _session_with_rows(*rows):
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = rows
    return session


def test_list_active_tutors_returns_delivery_context_in_stable_order():
    session = _session_with_rows(
        {
            "id": 1,
            "display_name": "Tutor One",
            "telegram_user_id": 100,
            "telegram_chat_id": 200,
        }
    )

    tutors = TutorRepository(session).list_active_tutors()

    assert tutors == [
        {
            "id": 1,
            "display_name": "Tutor One",
            "telegram_user_id": 100,
            "telegram_chat_id": 200,
        }
    ]
    statement = session.execute.call_args.args[0].text
    assert "FROM tutors" in statement
    assert "WHERE is_active = TRUE" in statement
    assert "ORDER BY display_name ASC, id ASC" in statement


def test_list_students_for_tutor_uses_assignment_mapping_and_student_details():
    session = _session_with_rows(
        {
            "id": 10,
            "student_number": "STU-010",
            "name": "Ada Student",
            "programme": "Business IT",
            "group_name": "BIT24",
        }
    )

    students = TutorRepository(session).list_students_for_tutor(3)

    assert students[0]["id"] == 10
    assert students[0]["name"] == "Ada Student"
    statement = session.execute.call_args.args[0].text
    params = session.execute.call_args.args[1]
    assert "FROM tutor_student_assignments AS assignment" in statement
    assert "INNER JOIN students AS s" in statement
    assert params == {"tutor_id": 3}


def test_list_active_tutor_recipients_for_student_requires_assignment_and_provisioned_ids():
    session = _session_with_rows(
        {
            "tutor_id": 3,
            "telegram_user_id": 100,
            "telegram_chat_id": 200,
            "student_display_name": "Ada Student",
        }
    )

    recipients = TutorRepository(session).list_active_tutor_recipients_for_student(10)

    assert recipients[0]["tutor_id"] == 3
    statement = session.execute.call_args.args[0].text
    params = session.execute.call_args.args[1]
    assert "FROM tutor_student_assignments AS assignment" in statement
    assert "INNER JOIN tutors AS tutor" in statement
    assert "tutor.is_active = TRUE" in statement
    assert "tutor.telegram_user_id IS NOT NULL" in statement
    assert "tutor.telegram_chat_id IS NOT NULL" in statement
    assert params == {"student_id": 10}


def test_get_teacher_by_id_returns_supported_contact_information():
    session = Mock()
    row = {
        "id": 3,
        "display_name": "Anna Example",
        "email": "anna@example.invalid",
        "is_active": True,
    }
    session.execute.return_value.mappings.return_value.first.return_value = row
    assert TutorRepository(session).get_by_id(3) == row


def test_search_teacher_by_name_is_case_insensitive():
    session = _session_with_rows({"id": 3, "display_name": "Anna Example"})
    assert TutorRepository(session).search_by_name("ANNA")[0]["id"] == 3
    _, params = session.execute.call_args.args
    assert params == {"name_pattern": "%anna%"}


def test_list_courses_for_teacher_supports_multiple_assignments():
    session = _session_with_rows(
        {"id": 1, "course_code": "DBS24", "assignment_role": "TEACHER"},
        {"id": 2, "course_code": "DIN24", "assignment_role": "LEAD_TEACHER"},
    )
    courses = TutorRepository(session).list_courses_for_teacher(3)
    assert [course["course_code"] for course in courses] == ["DBS24", "DIN24"]
    statement, params = session.execute.call_args.args
    assert "teacher_course_assignments" in statement.text
    assert params == {"tutor_id": 3}
