from unittest.mock import MagicMock

from app.repositories.progress_repository import ProgressRepository


def test_get_student_progress_data_returns_progress_data() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.first.return_value = {
        "student_id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "programme": "Business IT",
        "completed_ects": 90,
        "current_semester": 4,
    }

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = ProgressRepository(session)

    result = repository.get_student_progress_data(1)

    assert result == {
        "student_id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "programme": "Business IT",
        "completed_ects": 90,
        "current_semester": 4,
    }

    session.execute.assert_called_once()

    parameters = session.execute.call_args.args[1]
    assert parameters == {"student_id": 1}


def test_get_student_progress_data_returns_none_when_student_not_found() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.first.return_value = None

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = ProgressRepository(session)

    result = repository.get_student_progress_data(999)

    assert result is None

    parameters = session.execute.call_args.args[1]
    assert parameters == {"student_id": 999}


def test_get_expected_ects_returns_expected_value() -> None:
    session = MagicMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = 120
    session.execute.return_value = execute_result

    repository = ProgressRepository(session)

    result = repository.get_expected_ects(
        programme="Business IT",
        semester=4,
    )

    assert result == 120

    parameters = session.execute.call_args.args[1]

    assert parameters == {
        "programme": "Business IT",
        "semester": 4,
    }


def test_get_expected_ects_returns_none_when_curriculum_not_found() -> None:
    session = MagicMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execute_result

    repository = ProgressRepository(session)

    result = repository.get_expected_ects(
        programme="Unknown Programme",
        semester=4,
    )

    assert result is None