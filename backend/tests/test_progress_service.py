from unittest.mock import MagicMock

from app.services.progress_service import ProgressService


def test_get_progress_returns_behind_status() -> None:
    repository = MagicMock()

    repository.get_student_progress_data.return_value = {
        "student_id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "programme": "Business IT",
        "completed_ects": 90,
        "current_semester": 4,
    }
    repository.get_expected_ects.return_value = 120

    service = ProgressService(repository)

    result = service.get_progress(1)

    assert result["success"] is True

    progress = result["progress"]

    assert progress["student_id"] == 1
    assert progress["completed_ects"] == 90
    assert progress["expected_ects"] == 120
    assert progress["difference_ects"] == -30
    assert progress["remaining_to_expected_ects"] == 30
    assert progress["progress_percentage"] == 75.0
    assert progress["status"] == "BEHIND"

    repository.get_student_progress_data.assert_called_once_with(1)
    repository.get_expected_ects.assert_called_once_with(
        "Business IT",
        4,
    )


def test_get_progress_returns_on_track_status() -> None:
    repository = MagicMock()

    repository.get_student_progress_data.return_value = {
        "student_id": 2,
        "student_number": "S002",
        "name": "Anna Korhonen",
        "programme": "Data Engineering",
        "completed_ects": 120,
        "current_semester": 4,
    }
    repository.get_expected_ects.return_value = 120

    service = ProgressService(repository)

    result = service.get_progress(2)

    assert result["success"] is True
    assert result["progress"]["difference_ects"] == 0
    assert result["progress"]["remaining_to_expected_ects"] == 0
    assert result["progress"]["progress_percentage"] == 100.0
    assert result["progress"]["status"] == "ON_TRACK"


def test_get_progress_returns_ahead_status() -> None:
    repository = MagicMock()

    repository.get_student_progress_data.return_value = {
        "student_id": 3,
        "student_number": "S003",
        "name": "Leo Nieminen",
        "programme": "Cybersecurity",
        "completed_ects": 135,
        "current_semester": 4,
    }
    repository.get_expected_ects.return_value = 120

    service = ProgressService(repository)

    result = service.get_progress(3)

    assert result["success"] is True
    assert result["progress"]["difference_ects"] == 15
    assert result["progress"]["remaining_to_expected_ects"] == 0
    assert result["progress"]["progress_percentage"] == 112.5
    assert result["progress"]["status"] == "AHEAD"


def test_get_progress_rejects_invalid_student_id() -> None:
    repository = MagicMock()
    service = ProgressService(repository)

    result = service.get_progress(0)

    assert result == {
        "success": False,
        "error": "INVALID_STUDENT_ID",
        "message": "Student ID must be a positive integer.",
    }

    repository.get_student_progress_data.assert_not_called()
    repository.get_expected_ects.assert_not_called()


def test_get_progress_handles_missing_student() -> None:
    repository = MagicMock()
    repository.get_student_progress_data.return_value = None

    service = ProgressService(repository)

    result = service.get_progress(999)

    assert result == {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }

    repository.get_student_progress_data.assert_called_once_with(999)
    repository.get_expected_ects.assert_not_called()


def test_get_progress_handles_missing_curriculum() -> None:
    repository = MagicMock()

    repository.get_student_progress_data.return_value = {
        "student_id": 4,
        "student_number": "S004",
        "name": "Test Student",
        "programme": "Unknown Programme",
        "completed_ects": 60,
        "current_semester": 2,
    }
    repository.get_expected_ects.return_value = None

    service = ProgressService(repository)

    result = service.get_progress(4)

    assert result == {
        "success": False,
        "error": "CURRICULUM_NOT_FOUND",
        "message": (
            "Curriculum data was not found for programme "
            "'Unknown Programme' and semester 2."
        ),
    }

    repository.get_expected_ects.assert_called_once_with(
        "Unknown Programme",
        2,
    )


def test_get_progress_handles_zero_expected_ects() -> None:
    repository = MagicMock()

    repository.get_student_progress_data.return_value = {
        "student_id": 5,
        "student_number": "S005",
        "name": "Zero Curriculum Student",
        "programme": "Business IT",
        "completed_ects": 0,
        "current_semester": 1,
    }
    repository.get_expected_ects.return_value = 0

    service = ProgressService(repository)

    result = service.get_progress(5)

    assert result["success"] is True
    assert result["progress"]["progress_percentage"] == 0.0
    assert result["progress"]["status"] == "ON_TRACK"