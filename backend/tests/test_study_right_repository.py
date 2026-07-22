from datetime import date
from unittest.mock import Mock

from app.repositories.study_right_repository import StudyRightRepository


def test_get_by_student_id_returns_study_right() -> None:
    session = Mock()

    row = {
        "id": 1,
        "student_id": 1,
        "start_date": date(2021, 9, 1),
        "end_date": date(2027, 5, 31),
        "status": "ACTIVE",
        "extension_count": 0,
    }

    session.execute.return_value.mappings.return_value.first.return_value = row

    repository = StudyRightRepository(session)

    result = repository.get_by_student_id(1)

    assert result == row
    session.execute.assert_called_once()


def test_get_by_student_id_returns_none_when_missing() -> None:
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = None

    repository = StudyRightRepository(session)

    result = repository.get_by_student_id(999)

    assert result is None