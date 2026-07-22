from unittest.mock import Mock

from app.repositories.student_repository import StudentRepository


def test_get_by_id_returns_student_mapping() -> None:
    session = Mock()

    row = {
        "id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "group_name": "TT21A",
        "programme": "Business IT",
        "start_date": "2021-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    session.execute.return_value.mappings.return_value.first.return_value = row

    repository = StudentRepository(session)

    result = repository.get_by_id(1)

    assert result == row
    session.execute.assert_called_once()


def test_get_by_id_returns_none_when_student_is_missing() -> None:
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = None

    repository = StudentRepository(session)

    result = repository.get_by_id(999)

    assert result is None