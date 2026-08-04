"""Expected Academic Progress Service — Issue #92.

Calculates the expected ECTS credits a student should have completed
based on their programme curriculum and current semester.

Uses semester-based milestone lookup from the curriculum table —
the project's established business rule. There is no time-based
linear formula, duration_years field, or calendar date calculation
in this project.

Architecture:
    Database
        ↓
    CurriculumRepository / ProgressRepository
        ↓
    ExpectedProgressService   ← this file
        ↓
    MCP tools, Agents, future API endpoints (#93 will consume this)

Does NOT calculate completed ECTS (belongs to Issue #91).
Does NOT detect delayed students (belongs to Issue #93).
"""

from __future__ import annotations

from typing import Any

from app.repositories.progress_repository import ProgressRepository
from app.repositories.curriculum_repository import CurriculumRepository
from app.services.progress_service import ProgressService
from app.services.curriculum_service import CurriculumService


class ExpectedProgressService:
    """Calculates expected ECTS progress for a student.

    Uses the semester-based milestone lookup established in the project:
        expected_ects = curriculum.expected_ects
                        WHERE programme = <student_programme>
                          AND semester  = <student_current_semester>

    The current_semester is derived from the student's course completions
    (MAX(cc.semester)), which is the project's established convention.

    Supports multiple programmes without hard-coded conditionals.
    All programme/curriculum data comes from the database.

    Args:
        progress_service: Existing ProgressService (owns completed_ects and
                          current_semester derivation — Issue #91).
        curriculum_service: Existing CurriculumService (owns curriculum data).
    """

    def __init__(
        self,
        progress_service: ProgressService,
        curriculum_service: CurriculumService,
    ) -> None:
        self._progress_service = progress_service
        self._curriculum_service = curriculum_service

    def get_expected_progress(self, student_id: int) -> dict[str, Any]:
        """Calculate expected ECTS for a student at their current semester.

        Retrieves the student's current semester from course completion data,
        then looks up the curriculum milestone for that programme and semester.

        The curriculum table stores the expected cumulative ECTS for each
        semester (e.g. semester 1 = 30, semester 2 = 60, ..., semester 8 = 240).
        Expected ECTS equals the milestone for the student's current semester.

        Args:
            student_id: The numeric database ID of the student.

        Returns:
            A dict with:
            - success: True on success
            - expected_progress: nested dict with:
                - student_id, student_number, student_name, programme
                - current_semester: derived from MAX(course_completions.semester)
                - expected_ects: curriculum milestone for current semester
                - total_curriculum_ects: maximum milestone (graduation target)
                - remaining_to_graduation: total_curriculum_ects - completed_ects
                  (Note: completed_ects from Issue #91 is NOT recalculated here;
                   remaining_to_graduation uses expected milestone, not completed)
                - semester_milestones: full list of (semester, expected_ects) pairs

            Returns error dict on failure with success=False and error code.

        Error codes:
            INVALID_STUDENT_ID      — student_id <= 0
            STUDENT_NOT_FOUND       — no student row exists
            CURRICULUM_NOT_FOUND    — no curriculum rows for this programme
            SEMESTER_MILESTONE_NOT_FOUND — no curriculum row for current semester
        """
        # Validate input
        if not isinstance(student_id, int) or student_id <= 0:
            return {
                "success": False,
                "error": "INVALID_STUDENT_ID",
                "message": "Student ID must be a positive integer.",
            }

        # Get progress data — owns current_semester and student context
        progress_result = self._progress_service.get_progress(student_id)

        if not progress_result.get("success"):
            # Propagate STUDENT_NOT_FOUND and other errors intact
            return progress_result

        progress = progress_result["progress"]
        programme = progress.get("programme", "")
        current_semester = progress.get("current_semester", 1)
        student_id_confirmed = progress.get("student_id")
        student_number = progress.get("student_number", "")
        student_name = progress.get("student_name", "")

        # Get full curriculum for this programme — supports multiple programmes
        curriculum_result = self._curriculum_service.get_curriculum(programme)

        if not curriculum_result.get("success"):
            return {
                "success": False,
                "error": "CURRICULUM_NOT_FOUND",
                "message": (
                    f"Curriculum data not found for programme '{programme}'."
                ),
            }

        curriculum = curriculum_result["curriculum"]
        semesters = curriculum.get("semesters", [])
        total_curriculum_ects = curriculum.get("total_expected_ects", 0)

        # Find the milestone for the student's current semester
        expected_ects = _find_semester_milestone(semesters, current_semester)

        if expected_ects is None:
            return {
                "success": False,
                "error": "SEMESTER_MILESTONE_NOT_FOUND",
                "message": (
                    f"No curriculum milestone found for programme '{programme}' "
                    f"at semester {current_semester}."
                ),
            }

        # remaining_to_graduation: how many ECTS remain until graduation target
        remaining_to_graduation = max(total_curriculum_ects - expected_ects, 0)

        return {
            "success": True,
            "expected_progress": {
                "student_id": student_id_confirmed,
                "student_number": student_number,
                "student_name": student_name,
                "programme": programme,
                "current_semester": current_semester,
                "expected_ects": expected_ects,
                "total_curriculum_ects": total_curriculum_ects,
                "remaining_to_graduation": remaining_to_graduation,
                "semester_milestones": semesters,
            },
        }

    def get_expected_ects_for_semester(
        self,
        programme: str,
        semester: int,
    ) -> dict[str, Any]:
        """Get the expected ECTS milestone for a specific programme and semester.

        Useful for #93 (detect delayed students) which needs to compare
        a student's completed ECTS against the expected milestone for their semester.

        Args:
            programme: Programme name (e.g. "Business IT").
            semester: Semester number (1–8).

        Returns:
            Dict with success status and expected_ects integer, or error.
        """
        if not programme or not programme.strip():
            return {
                "success": False,
                "error": "INVALID_PROGRAMME",
                "message": "Programme must not be empty.",
            }

        if not isinstance(semester, int) or semester < 1:
            return {
                "success": False,
                "error": "INVALID_SEMESTER",
                "message": "Semester must be a positive integer.",
            }

        curriculum_result = self._curriculum_service.get_curriculum(programme)
        if not curriculum_result.get("success"):
            return {
                "success": False,
                "error": "CURRICULUM_NOT_FOUND",
                "message": (
                    f"Curriculum data not found for programme '{programme}'."
                ),
            }

        semesters = curriculum_result["curriculum"].get("semesters", [])
        expected_ects = _find_semester_milestone(semesters, semester)

        if expected_ects is None:
            return {
                "success": False,
                "error": "SEMESTER_MILESTONE_NOT_FOUND",
                "message": (
                    f"No milestone for programme '{programme}' "
                    f"at semester {semester}."
                ),
            }

        return {
            "success": True,
            "programme": programme,
            "semester": semester,
            "expected_ects": expected_ects,
        }


def _find_semester_milestone(
    semesters: list[dict[str, Any]],
    target_semester: int,
) -> int | None:
    """Find the expected_ects milestone for a target semester.

    Args:
        semesters: List of dicts with "semester" and "expected_ects" keys.
        target_semester: The semester number to look up.

    Returns:
        The expected_ects integer for that semester, or None if not found.
    """
    for row in semesters:
        if int(row["semester"]) == target_semester:
            return int(row["expected_ects"])
    return None
