"""Unit tests for get_student_dashboard MCP tool — Issue #77."""

from unittest.mock import Mock, patch, MagicMock

import pytest

from app.mcp.tools.student_dashboard import (
    _memoize_request_evidence,
    get_student_dashboard,
)


def _make_success_dashboard(student_id=1):
    return {
        "success": True,
        "student_id": student_id,
        "dashboard": {
            "profile": {"student_id": student_id, "student_number": "S001",
                        "name": "Mikael Virtanen"},
            "academic_progress": {"available": True, "completed_ects": 120},
            "study_right": {"available": True, "status": "ACTIVE"},
            "academic_health": {
                "success": True, "assessment_status": "COMPLETE",
                "health_score": 100, "health_level": "STRONG",
            },
            "risk": {"current_analysis": {"risk_level": "LOW"}, "events": []},
            "upcoming_actions": {"academic_events": [], "tutor_meetings": [],
                                 "recommended_actions": []},
            "summary": {"overall_status": "ON_TRACK", "attention_required": False,
                        "priority": "LOW", "key_findings": []},
        },
    }


def test_request_evidence_memoization_avoids_duplicate_service_reads():
    student, progress, study_right, event = Mock(), Mock(), Mock(), Mock()
    student_call = student.get_student
    progress_call = progress.get_progress
    study_right_call = study_right.get_study_right
    event_call = event.get_upcoming_events
    _memoize_request_evidence(student, progress, study_right, event)

    student.get_student(1)
    student.get_student(1)
    progress.get_progress(1)
    progress.get_progress(1)
    study_right.get_study_right(1)
    study_right.get_study_right(1)
    event.get_upcoming_events(start_date="2026-08-08", end_date=None)
    event.get_upcoming_events(start_date="2026-08-08", end_date=None)

    student_call.assert_called_once_with(1)
    progress_call.assert_called_once_with(1)
    study_right_call.assert_called_once_with(1)
    event_call.assert_called_once_with(start_date="2026-08-08", end_date=None)


def test_separate_requests_have_independent_memoization_scopes():
    first = [Mock(), Mock(), Mock(), Mock()]
    second = [Mock(), Mock(), Mock(), Mock()]
    first_call = first[0].get_student
    second_call = second[0].get_student
    first_call.return_value = {"success": True, "student": {"id": 1}}
    second_call.return_value = {"success": True, "student": {"id": 1, "request": 2}}
    _memoize_request_evidence(*first)
    _memoize_request_evidence(*second)

    assert first[0].get_student(1) != second[0].get_student(1)
    first[0].get_student(1)
    second[0].get_student(1)

    first_call.assert_called_once_with(1)
    second_call.assert_called_once_with(1)


def test_student_ids_use_distinct_request_cache_keys():
    services = [Mock(), Mock(), Mock(), Mock()]
    student_call = services[0].get_student
    student_call.side_effect = lambda student_id: {
        "success": True,
        "student": {"id": student_id},
    }
    _memoize_request_evidence(*services)

    assert services[0].get_student(1)["student"]["id"] == 1
    assert services[0].get_student(2)["student"]["id"] == 2
    assert services[0].get_student(1)["student"]["id"] == 1
    assert student_call.call_count == 2


def test_memoization_does_not_cache_exceptions():
    services = [Mock(), Mock(), Mock(), Mock()]
    progress_call = services[1].get_progress
    progress_call.side_effect = [RuntimeError("temporary"), {"success": True}]
    _memoize_request_evidence(*services)

    with pytest.raises(RuntimeError, match="temporary"):
        services[1].get_progress(1)
    assert services[1].get_progress(1) == {"success": True}
    assert progress_call.call_count == 2


def test_unsuccessful_evidence_is_cached_without_being_upgraded():
    services = [Mock(), Mock(), Mock(), Mock()]
    study_right_call = services[2].get_study_right
    unavailable = {"success": False, "error": "STUDY_RIGHT_NOT_FOUND"}
    study_right_call.return_value = unavailable
    _memoize_request_evidence(*services)

    first = services[2].get_study_right(1)
    second = services[2].get_study_right(1)

    assert first is unavailable
    assert second is unavailable
    assert first["success"] is False
    study_right_call.assert_called_once_with(1)


@patch("app.mcp.tools.student_dashboard.SessionLocal")
@patch("app.mcp.tools.student_dashboard.StudentDashboardService")
@patch("app.mcp.tools.student_dashboard.AcademicHealthScoreService")
def test_tool_returns_dashboard_on_success(
    health_service_cls: Mock,
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
    wiring = dashboard_service_cls.call_args.kwargs
    canonical_risk = wiring["academic_risk_service"]
    health_service_cls.assert_called_once_with(canonical_risk)
    assert wiring["academic_health_service"] is health_service_cls.return_value
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
