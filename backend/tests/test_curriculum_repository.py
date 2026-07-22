from unittest.mock import MagicMock

from app.repositories.curriculum_repository import CurriculumRepository


def test_get_by_programme_returns_curriculum_rows() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = [
        {
            "programme": "Business IT",
            "semester": 1,
            "expected_ects": 30,
        },
        {
            "programme": "Business IT",
            "semester": 2,
            "expected_ects": 60,
        },
    ]

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = CurriculumRepository(session)

    result = repository.get_by_programme("Business IT")

    assert result == [
        {
            "programme": "Business IT",
            "semester": 1,
            "expected_ects": 30,
        },
        {
            "programme": "Business IT",
            "semester": 2,
            "expected_ects": 60,
        },
    ]

    session.execute.assert_called_once()

    parameters = session.execute.call_args.args[1]
    assert parameters == {"programme": "Business IT"}


def test_get_by_programme_returns_empty_list_when_not_found() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = []

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = CurriculumRepository(session)

    result = repository.get_by_programme("Unknown Programme")

    assert result == []