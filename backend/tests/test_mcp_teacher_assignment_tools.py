from unittest.mock import Mock, patch

from app.mcp.tools import teacher_assignments


def test_get_course_teachers_delegates_identifiers_role_and_closes() -> None:
    session = Mock()
    service = Mock()
    service.get_course_teachers.return_value = {"success": True, "teachers": []}
    with patch.object(teacher_assignments, "SessionLocal", return_value=session), patch.object(
        teacher_assignments, "_service", return_value=service
    ):
        result = teacher_assignments.get_course_teachers(
            course_code="DII101",
            role="LEAD_TEACHER",
        )
    assert result["success"] is True
    service.get_course_teachers.assert_called_once_with(
        course_id=None,
        course_code="DII101",
        role="LEAD_TEACHER",
    )
    session.close.assert_called_once_with()


def test_get_teacher_courses_returns_stable_database_error() -> None:
    session = Mock()
    service = Mock()
    service.get_teacher_courses.side_effect = RuntimeError("private database detail")
    with patch.object(teacher_assignments, "SessionLocal", return_value=session), patch.object(
        teacher_assignments, "_service", return_value=service
    ):
        result = teacher_assignments.get_teacher_courses(8)
    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Teacher course assignments could not be retrieved.",
    }
    session.close.assert_called_once_with()
