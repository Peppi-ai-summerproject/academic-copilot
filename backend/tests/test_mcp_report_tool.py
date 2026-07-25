import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

from sqlalchemy.exc import SQLAlchemyError

from app.mcp.tools.report import generate_report


@patch("app.db.database.SessionLocal")
@patch("app.mcp.tools.report.ReportService")
def test_generate_report_tool_returns_report(
    mock_report_service_class: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    session = MagicMock()
    report_service = MagicMock()

    mock_session_local.return_value = session
    mock_report_service_class.return_value = report_service
    report_service.generate_report.return_value = {
        "success": True,
        "report": {
            "report_type": "academic_summary",
            "generated_at": "2026-07-25T22:00:00Z",
            "student": {"id": 1},
            "academic_progress": {},
            "study_right": {},
            "curriculum": {},
            "risk_assessment": None,
            "upcoming_events": [],
            "summary": {"overall_status": "UNKNOWN", "key_findings": [], "recommended_actions": [], "warnings": []},
        },
    }

    result = generate_report(1)

    assert result["success"] is True
    report_service.generate_report.assert_called_once_with(1, report_type="academic_summary")
    session.close.assert_called_once()


@patch("app.db.database.SessionLocal")
@patch("app.mcp.tools.report.ReportService")
def test_generate_report_tool_returns_student_not_found(
    mock_report_service_class: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    session = MagicMock()
    report_service = MagicMock()

    mock_session_local.return_value = session
    mock_report_service_class.return_value = report_service
    report_service.generate_report.return_value = {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }

    result = generate_report(999)

    assert result == {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }
    session.close.assert_called_once()


@patch("app.db.database.SessionLocal")
def test_generate_report_tool_converts_database_error(
    mock_session_local: MagicMock,
) -> None:
    session = MagicMock()
    mock_session_local.return_value = session

    with patch(
        "app.mcp.tools.report.StudentRepository",
        side_effect=SQLAlchemyError("Database unavailable"),
    ):
        result = generate_report(1)

    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Failed to generate the academic report.",
    }
    session.close.assert_called_once()


@patch("app.db.database.SessionLocal")
@patch("app.mcp.tools.report.ReportService")
def test_generate_report_tool_forwards_report_type(
    mock_report_service_class: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    session = MagicMock()
    report_service = MagicMock()

    mock_session_local.return_value = session
    mock_report_service_class.return_value = report_service
    report_service.generate_report.return_value = {
        "success": True,
        "report": {
            "report_type": "academic_summary",
            "generated_at": "2026-07-25T22:00:00Z",
            "student": {"id": 1},
            "academic_progress": {},
            "study_right": {},
            "curriculum": {},
            "risk_assessment": None,
            "upcoming_events": [],
            "summary": {"overall_status": "UNKNOWN", "key_findings": [], "recommended_actions": [], "warnings": []},
        },
    }

    result = generate_report(1, report_type="academic_summary")

    assert result["success"] is True
    report_service.generate_report.assert_called_once_with(1, report_type="academic_summary")
    session.close.assert_called_once()
