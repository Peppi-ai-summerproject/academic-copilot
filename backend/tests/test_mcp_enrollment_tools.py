from unittest.mock import Mock, patch

from app.mcp.tools import enrollments


def test_course_roster_delegates_and_closes_session() -> None:
    session = Mock()
    service = Mock()
    service.get_course_roster.return_value = {"success": True, "students": []}
    with patch.object(enrollments, "SessionLocal", return_value=session), patch.object(
        enrollments, "_service", return_value=service
    ):
        result = enrollments.get_course_roster(1, "ENROLLED")
    assert result["success"] is True
    service.get_course_roster.assert_called_once_with(1, "ENROLLED")
    session.close.assert_called_once_with()


def test_student_enrollments_returns_stable_database_error() -> None:
    session = Mock()
    service = Mock()
    service.get_student_enrollments.side_effect = RuntimeError("secret database detail")
    with patch.object(enrollments, "SessionLocal", return_value=session), patch.object(
        enrollments, "_service", return_value=service
    ):
        result = enrollments.get_student_enrollments(7)
    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Student enrollments could not be retrieved.",
    }
    session.close.assert_called_once_with()


def test_individual_enrollment_delegates_both_ids() -> None:
    session = Mock()
    service = Mock()
    service.get_enrollment.return_value = {"success": True, "enrollment": {}}
    with patch.object(enrollments, "SessionLocal", return_value=session), patch.object(
        enrollments, "_service", return_value=service
    ):
        result = enrollments.get_enrollment(7, 1)
    assert result["success"] is True
    service.get_enrollment.assert_called_once_with(7, 1)
    session.close.assert_called_once_with()
