from datetime import date
from unittest.mock import Mock

from app.services.study_right_service import StudyRightService


def test_get_study_right_returns_active_status() -> None:
    repository = Mock()
    repository.get_by_student_id.return_value = {
        "id": 1,
        "student_id": 1,
        "start_date": date(2021, 9, 1),
        "end_date": date(2027, 5, 31),
        "status": "ACTIVE",
        "extension_count": 0,
    }

    service = StudyRightService(repository)

    result = service.get_study_right(1)

    assert result["success"] is True
    assert result["study_right"]["status"] == "ACTIVE"
    assert result["study_right"]["expiration_date"] == date(2027, 5, 31)
    assert result["study_right"]["is_expiring_soon"] is False


def test_get_study_right_detects_expiring_status() -> None:
    repository = Mock()
    repository.get_by_student_id.return_value = {
        "id": 2,
        "student_id": 2,
        "start_date": date(2021, 9, 1),
        "end_date": date(2025, 7, 31),
        "status": "EXPIRES_SOON",
        "extension_count": 1,
    }

    service = StudyRightService(repository)

    result = service.get_study_right(2)

    assert result["success"] is True
    assert result["study_right"]["status"] == "EXPIRES_SOON"
    assert result["study_right"]["is_expiring_soon"] is True


def test_get_study_right_handles_missing_record() -> None:
    repository = Mock()
    repository.get_by_student_id.return_value = None

    service = StudyRightService(repository)

    result = service.get_study_right(999)

    assert result["success"] is False
    assert result["error"] == "STUDY_RIGHT_NOT_FOUND"


def test_get_study_right_rejects_invalid_student_id() -> None:
    repository = Mock()

    service = StudyRightService(repository)

    result = service.get_study_right(0)

    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"
    repository.get_by_student_id.assert_not_called()