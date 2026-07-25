from datetime import date
from unittest.mock import MagicMock

from app.services.risk_service import RiskService


def make_student(
    completed_ects: int,
    expected_ects: int,
    study_right_status: str = "ACTIVE",
) -> dict:
    return {
        "student_id": 1,
        "student_number": "S001",
        "student_name": "Mikael Virtanen",
        "group_name": "TT21A",
        "programme": "Business IT",
        "programme_code": "DIN2024S",
        "student_status": "ACTIVE",
        "completed_ects": completed_ects,
        "current_semester": 7,
        "expected_ects": expected_ects,
        "study_right_status": study_right_status,
        "study_right_start_date": date(2021, 9, 1),
        "study_right_end_date": date(2027, 5, 31),
        "extension_count": 0,
    }


def test_find_students_at_risk_returns_high_risk_student() -> None:
    repository = MagicMock()
    repository.get_students_for_risk_analysis.return_value = [
        make_student(
            completed_ects=65,
            expected_ects=210,
        )
    ]

    service = RiskService(repository)

    result = service.find_students_at_risk()

    assert result["success"] is True
    assert result["risk_summary"]["total_at_risk"] == 1
    assert result["risk_summary"]["high_risk"] == 1
    assert result["students"][0]["risk_level"] == "HIGH"
    assert result["students"][0]["difference_ects"] == -145
    assert len(result["students"][0]["risk_reasons"]) == 1


def test_find_students_at_risk_returns_medium_risk_student() -> None:
    repository = MagicMock()
    repository.get_students_for_risk_analysis.return_value = [
        make_student(
            completed_ects=70,
            expected_ects=90,
        )
    ]

    service = RiskService(repository)

    result = service.find_students_at_risk()

    assert result["risk_summary"]["medium_risk"] == 1
    assert result["students"][0]["risk_level"] == "MEDIUM"


def test_find_students_at_risk_ignores_low_risk_student() -> None:
    repository = MagicMock()
    repository.get_students_for_risk_analysis.return_value = [
        make_student(
            completed_ects=90,
            expected_ects=90,
        )
    ]

    service = RiskService(repository)

    result = service.find_students_at_risk()

    assert result["risk_summary"]["total_students_analysed"] == 1
    assert result["risk_summary"]["total_at_risk"] == 0
    assert result["students"] == []


def test_find_students_at_risk_detects_expiring_study_right() -> None:
    repository = MagicMock()
    repository.get_students_for_risk_analysis.return_value = [
        make_student(
            completed_ects=90,
            expected_ects=90,
            study_right_status="EXPIRES_SOON",
        )
    ]

    service = RiskService(repository)

    result = service.find_students_at_risk()

    student = result["students"][0]

    assert student["risk_level"] == "MEDIUM"
    assert "Study right expires soon." in student["risk_reasons"]


def test_find_students_at_risk_expired_study_right_is_high() -> None:
    repository = MagicMock()
    repository.get_students_for_risk_analysis.return_value = [
        make_student(
            completed_ects=90,
            expected_ects=90,
            study_right_status="EXPIRED",
        )
    ]

    service = RiskService(repository)

    result = service.find_students_at_risk()

    student = result["students"][0]

    assert student["risk_level"] == "HIGH"
    assert "Study right has expired." in student["risk_reasons"]


def test_find_students_at_risk_supports_programme_filter() -> None:
    repository = MagicMock()
    repository.get_students_for_risk_analysis.return_value = []

    service = RiskService(repository)

    result = service.find_students_at_risk(
        programme_code="DIN2024S",
    )

    repository.get_students_for_risk_analysis.assert_called_once_with(
        programme_code="DIN2024S",
    )

    assert result["filters"]["programme_code"] == "DIN2024S"


def test_find_students_at_risk_returns_empty_result() -> None:
    repository = MagicMock()
    repository.get_students_for_risk_analysis.return_value = []

    service = RiskService(repository)

    result = service.find_students_at_risk()

    assert result["success"] is True
    assert result["risk_summary"]["total_students_analysed"] == 0
    assert result["risk_summary"]["total_at_risk"] == 0
    assert result["students"] == []
    