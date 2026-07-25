from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

from app.mcp.tools.risk import find_students_at_risk


@patch("app.mcp.tools.risk.RiskService")
@patch("app.mcp.tools.risk.RiskRepository")
@patch("app.mcp.tools.risk.SessionLocal")
def test_find_students_at_risk_success(
    mock_session_local: MagicMock,
    mock_repository_class: MagicMock,
    mock_service_class: MagicMock,
) -> None:
    db = MagicMock()
    mock_session_local.return_value = db

    repository = MagicMock()
    mock_repository_class.return_value = repository

    service = MagicMock()
    service.find_students_at_risk.return_value = {
        "success": True,
        "risk_summary": {
            "total_students_analysed": 1,
            "total_at_risk": 1,
            "high_risk": 1,
            "medium_risk": 0,
        },
        "students": [
            {
                "student_id": 1,
                "risk_level": "HIGH",
                "risk_reasons": [
                    "Student is 145 ECTS behind expected progression."
                ],
            }
        ],
    }
    mock_service_class.return_value = service

    result = find_students_at_risk(
        programme_code="DIN2024S",
    )

    assert result["success"] is True
    assert result["students"][0]["risk_level"] == "HIGH"

    service.find_students_at_risk.assert_called_once_with(
        programme_code="DIN2024S",
    )

    db.close.assert_called_once()


@patch("app.mcp.tools.risk.RiskService")
@patch("app.mcp.tools.risk.RiskRepository")
@patch("app.mcp.tools.risk.SessionLocal")
def test_find_students_at_risk_returns_empty_result(
    mock_session_local: MagicMock,
    mock_repository_class: MagicMock,
    mock_service_class: MagicMock,
) -> None:
    db = MagicMock()
    mock_session_local.return_value = db

    repository = MagicMock()
    mock_repository_class.return_value = repository

    service = MagicMock()
    service.find_students_at_risk.return_value = {
        "success": True,
        "risk_summary": {
            "total_students_analysed": 0,
            "total_at_risk": 0,
            "high_risk": 0,
            "medium_risk": 0,
        },
        "students": [],
    }
    mock_service_class.return_value = service

    result = find_students_at_risk()

    assert result["success"] is True
    assert result["students"] == []

    db.close.assert_called_once()


@patch("app.mcp.tools.risk.SessionLocal")
def test_find_students_at_risk_database_error(
    mock_session_local: MagicMock,
) -> None:
    db = MagicMock()
    mock_session_local.return_value = db

    db.execute.side_effect = SQLAlchemyError("database failure")

    with patch(
        "app.mcp.tools.risk.RiskService.find_students_at_risk",
        side_effect=SQLAlchemyError("database failure"),
    ):
        result = find_students_at_risk()

    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Failed to identify students at risk.",
    }

    db.close.assert_called_once()