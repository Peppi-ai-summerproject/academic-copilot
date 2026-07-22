from typing import Any


def get_curriculum(
    programme: str,
    semester: int | None = None,
) -> dict[str, Any]:
    """
    Retrieve curriculum requirements and expected study progression.

    Args:
        programme: Name of the study programme.
        semester: Optional semester number.

    Returns:
        Curriculum information including expected ECTS and courses.
    """

    if not programme or not programme.strip():
        return {
            "success": False,
            "error": "INVALID_PROGRAMME",
            "message": "Programme must be provided.",
        }

    if semester is not None and semester < 1:
        return {
            "success": False,
            "error": "INVALID_SEMESTER",
            "message": "Semester must be greater than zero.",
        }

    normalized_programme = programme.strip()

    # Temporary placeholder.
    # Replace this section with the project's database/repository query.
    curriculum_data = None

    if curriculum_data is None:
        semester_text = (
            f" and semester {semester}"
            if semester is not None
            else ""
        )

        return {
            "success": False,
            "error": "CURRICULUM_NOT_FOUND",
            "message": (
                f"Curriculum data was not found for programme "
                f"'{normalized_programme}'{semester_text}."
            ),
        }

    return {
        "success": True,
        "programme": normalized_programme,
        "semester": semester,
        "expected_ects": curriculum_data["expected_ects"],
        "total_curriculum_ects": curriculum_data.get(
            "total_curriculum_ects"
        ),
        "courses": curriculum_data.get("courses", []),
    }