"""Unit tests for get_student_dashboard MCP tool — Issue #77."""

from unittest.mock import Mock, patch, MagicMock

from app.mcp.tools.student_dashboard import get_student_dashboard


def _make_success_dashboard(student_id=1):
    return {
        "success": True,
        "student_id": student_id,
        "dashboard": {
            "profile": {"student_id": student_id, "student_number": "S001",
                        "name": "Mikael Virtanen"},
            "academic_progress": {"available": True, "completed_ects": 120},
            "study_right": {"available": True, "status": "ACTIVE"},
            "risk": {"current_analysis": {"risk_level": "LOW"}, "events": []},
            "upcoming_actions": {"academic_events": [], "tutor_meetings": [],
                                 "recommended_actions": []},
            "summary": {"overall_status": "ON_TRACK", "attention_required": False,
                        "priority": "LOW", "key_findings": []},
        },
    }


@patch("app.mcp.tools.student_dashboard.SessionLocal")
@patch("app.mcp.tools.student_dashboard.StudentDashboardService")
def test_tool_returns_dashboard_on_success(
    dashboard_service_cls: Mock,
    session_local_mock: Mock,
) -> None:
    db = Mock()
    session_local_mock.return_value = db
    service_instance = Mock()
    service_instance.get_student_dashboard.return_value = _make_success_dashboard(1)
    dashboard_service_cls.return_value = service_instance

    result = get_student_dashboard(student_id=1)

    assert result["success"] is True
    assert result["student_id"] == 1
    assert "dashboard" in result
    db.close.assert_called_once()


@patch("app.mcp.tools.student_dashboard.SessionLocal")
@patch("app.mcp.tools.student_dashboard.StudentDashboardService")
def test_tool_passes_student_id_to_service(
    dashboard_service_cls: Mock,
    session_local_mock: Mock,
) -> None:
    db = Mock()
    session_local_mock.return_value = db
    service_instance = Mock()
    service_instance.get_student_dashboard.return_value = _make_success_dashboard(42)
    dashboard_service_cls.return_value = service_instance

    get_student_dashboard(student_id=42)

    service_instance.get_student_dashboard.assert_called_once_with(42)


@patch("app.mcp.tools.student_dashboard.SessionLocal")
@patch("app.mcp.tools.student_dashboard.StudentDashboardService")
def test_tool_returns_student_not_found_error(
    dashboard_service_cls: Mock,
    session_local_mock: Mock,
) -> None:
    db = Mock()
    session_local_mock.return_value = db
    service_instance = Mock()
    service_instance.get_student_dashboard.return_value = {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student was not found.",
    }
    dashboard_service_cls.return_value = service_instance

    result = get_student_dashboard(student_id=999)

    assert result["success"] is False
    assert result["error"] == "STUDENT_NOT_FOUND"
    db.close.assert_called_once()


@patch("app.mcp.tools.student_dashboard.SessionLocal")
def test_tool_returns_database_error_on_exception(
    session_local_mock: Mock,
) -> None:
    db = Mock()
    session_local_mock.return_value = db
    db.execute = Mock(side_effect=RuntimeError("DB crash"))

    result = get_student_dashboard(student_id=1)

    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"
    assert "message" in result
    db.close.assert_called_once()


@patch("app.mcp.tools.student_dashboard.SessionLocal")
@patch("app.mcp.tools.student_dashboard.StudentDashboardService")
def test_session_closes_on_success(
    dashboard_service_cls: Mock,
    session_local_mock: Mock,
) -> None:
    db = Mock()
    session_local_mock.return_value = db
    service_instance = Mock()
    service_instance.get_student_dashboard.return_value = _make_success_dashboard()
    dashboard_service_cls.return_value = service_instance

    get_student_dashboard(student_id=1)

    db.close.assert_called_once()


@patch("app.mcp.tools.student_dashboard.SessionLocal")
def test_session_closes_on_error(session_local_mock: Mock) -> None:
    db = Mock()
    session_local_mock.return_value = db
    db.close = Mock()

    with patch("app.mcp.tools.student_dashboard.StudentDashboardService",
               side_effect=RuntimeError("fail")):
        get_student_dashboard(student_id=1)

    db.close.assert_called_once()


@patch("app.mcp.tools.student_dashboard.SessionLocal")
@patch("app.mcp.tools.student_dashboard.StudentDashboardService")
def test_tool_preserves_service_response(
    dashboard_service_cls: Mock,
    session_local_mock: Mock,
) -> None:
    """MCP tool must not modify the service response."""
    db = Mock()
    session_local_mock.return_value = db
    expected = _make_success_dashboard()
    service_instance = Mock()
    service_instance.get_student_dashboard.return_value = expected
    dashboard_service_cls.return_value = service_instance

    result = get_student_dashboard(student_id=1)

    assert result == expected
