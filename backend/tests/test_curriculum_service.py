from unittest.mock import MagicMock

from app.services.curriculum_service import CurriculumService


def test_get_curriculum_returns_curriculum_information() -> None:
    repository = MagicMock()
    repository.get_by_programme.return_value = [
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
        {
            "programme": "Business IT",
            "semester": 3,
            "expected_ects": 90,
        },
    ]

    service = CurriculumService(repository)

    result = service.get_curriculum("Business IT")

    assert result == {
        "success": True,
        "curriculum": {
            "programme": "Business IT",
            "semesters": [
                {
                    "semester": 1,
                    "expected_ects": 30,
                },
                {
                    "semester": 2,
                    "expected_ects": 60,
                },
                {
                    "semester": 3,
                    "expected_ects": 90,
                },
            ],
            "total_expected_ects": 90,
        },
    }

    repository.get_by_programme.assert_called_once_with("Business IT")


def test_get_curriculum_strips_programme_whitespace() -> None:
    repository = MagicMock()
    repository.get_by_programme.return_value = [
        {
            "programme": "Business IT",
            "semester": 1,
            "expected_ects": 30,
        }
    ]

    service = CurriculumService(repository)

    result = service.get_curriculum("  Business IT  ")

    assert result["success"] is True
    repository.get_by_programme.assert_called_once_with("Business IT")


def test_get_curriculum_returns_error_for_empty_programme() -> None:
    repository = MagicMock()

    service = CurriculumService(repository)

    result = service.get_curriculum("   ")

    assert result == {
        "success": False,
        "error": "INVALID_PROGRAMME",
        "message": "Programme must not be empty.",
    }

    repository.get_by_programme.assert_not_called()


def test_get_curriculum_returns_not_found_error() -> None:
    repository = MagicMock()
    repository.get_by_programme.return_value = []

    service = CurriculumService(repository)

    result = service.get_curriculum("Unknown Programme")

    assert result == {
        "success": False,
        "error": "CURRICULUM_NOT_FOUND",
        "message": (
            "Curriculum data was not found for programme "
            "'Unknown Programme'."
        ),
    }