from unittest.mock import Mock

from app.services.student_service import StudentService


def test_get_student_returns_student_profile() -> None:
    repository = Mock()
    repository.get_by_id.return_value = {
        "id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "group_name": "TT21A",
        "programme": "Business IT",
        "start_date": "2021-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    service = StudentService(repository)

    result = service.get_student(1)

    assert result["success"] is True
    assert result["student"]["id"] == 1
    assert result["student"]["student_number"] == "S001"
    assert result["student"]["name"] == "Mikael Virtanen"

    repository.get_by_id.assert_called_once_with(1)


def test_get_student_handles_missing_student() -> None:
    repository = Mock()
    repository.get_by_id.return_value = None

    service = StudentService(repository)

    result = service.get_student(999)

    assert result == {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }

    repository.get_by_id.assert_called_once_with(999)


def test_get_student_rejects_invalid_student_id() -> None:
    repository = Mock()

    service = StudentService(repository)

    result = service.get_student(0)

    assert result == {
        "success": False,
        "error": "INVALID_STUDENT_ID",
        "message": "Student ID must be a positive integer.",
    }

    repository.get_by_id.assert_not_called()