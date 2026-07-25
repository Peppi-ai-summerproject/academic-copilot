from datetime import date
from unittest.mock import MagicMock

from app.repositories.risk_repository import RiskRepository


def test_get_students_for_risk_analysis_returns_students() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = [
        {
            "student_id": 1,
            "student_number": "S001",
            "student_name": "Mikael Virtanen",
            "group_name": "TT21A",
            "programme": "Business IT",
            "programme_code": "DIN2024S",
            "student_status": "ACTIVE",
            "completed_ects": 65,
            "current_semester": 7,
            "expected_ects": 210,
            "study_right_status": "ACTIVE",
            "study_right_start_date": date(2021, 9, 1),
            "study_right_end_date": date(2027, 5, 31),
            "extension_count": 0,
        }
    ]

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = RiskRepository(session)

    result = repository.get_students_for_risk_analysis()

    assert len(result) == 1
    assert result[0]["student_id"] == 1
    assert result[0]["completed_ects"] == 65
    assert result[0]["expected_ects"] == 210
    assert result[0]["study_right_status"] == "ACTIVE"

    session.execute.assert_called_once()

    parameters = session.execute.call_args.args[1]
    assert parameters == {}


def test_get_students_for_risk_analysis_supports_programme_filter() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = []

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = RiskRepository(session)

    result = repository.get_students_for_risk_analysis(
        programme_code="DIN2024S",
    )

    assert result == []

    parameters = session.execute.call_args.args[1]
    assert parameters == {
        "programme_code": "DIN2024S",
    }


def test_get_students_for_risk_analysis_returns_empty_list() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = []

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = RiskRepository(session)

    result = repository.get_students_for_risk_analysis()

    assert result == []