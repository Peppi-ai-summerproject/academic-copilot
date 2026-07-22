from typing import Any

from app.repositories.curriculum_repository import CurriculumRepository


class CurriculumService:
    """Business logic for curriculum information."""

    def __init__(self, repository: CurriculumRepository) -> None:
        self._repository = repository

    def get_curriculum(self, programme: str) -> dict[str, Any]:
        normalized_programme = programme.strip()

        if not normalized_programme:
            return {
                "success": False,
                "error": "INVALID_PROGRAMME",
                "message": "Programme must not be empty.",
            }

        rows = self._repository.get_by_programme(normalized_programme)

        if not rows:
            return {
                "success": False,
                "error": "CURRICULUM_NOT_FOUND",
                "message": (
                    f"Curriculum data was not found for programme "
                    f"'{normalized_programme}'."
                ),
            }

        semesters = [
            {
                "semester": int(row["semester"]),
                "expected_ects": int(row["expected_ects"]),
            }
            for row in rows
        ]

        total_expected_ects = max(
            semester["expected_ects"]
            for semester in semesters
        )

        return {
            "success": True,
            "curriculum": {
                "programme": str(rows[0]["programme"]),
                "semesters": semesters,
                "total_expected_ects": total_expected_ects,
            },
        }