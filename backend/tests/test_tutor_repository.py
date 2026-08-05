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
