"""ECTS Progress Analytics Service — Issue #91.

Calculates total completed ECTS credits for students using course completion
data. Provides analytics over individual students and student cohorts.

Reuses ProgressRepository and ProgressService — does not duplicate
existing business logic.
"""

from __future__ import annotations

from typing import Any

from app.repositories.progress_repository import ProgressRepository
from app.services.progress_service import ProgressService


class EctsAnalyticsService:
    """Calculates and stores ECTS progress analytics for students.

    Wraps the existing ProgressService to provide:
    - Individual student ECTS totals
    - Cohort-level ECTS summaries
    - Progress status categorisation (BEHIND / ON_TRACK / AHEAD)

    Responsibilities:
    - Calculate total completed ECTS per student
    - Compare actual ECTS to expected curriculum milestones
    - Return structured results for storage or API responses
    - Support batch calculation for multiple students

    Does NOT duplicate ProgressService logic.
    Does NOT call any LLM or external API.
    Does NOT access the database directly — delegates to ProgressService.

    Args:
        progress_service: Existing ProgressService instance.
    """

    def __init__(self, progress_service: ProgressService) -> None:
        self._progress_service = progress_service

    def calculate_ects_progress(self, student_id: int) -> dict[str, Any]:
        """Calculate total completed ECTS credits for a single student.

        Retrieves course completion data and curriculum requirements via the
        existing ProgressService, then returns a structured analytics result.

        Args:
            student_id: The numeric database ID of the student.

        Returns:
            A dict with success status and ECTS analytics data including:
            - student_id, student_number, student_name, programme
            - completed_ects: total credits completed
            - expected_ects: credits expected by current semester
            - difference_ects: difference (positive = ahead, negative = behind)
            - progress_percentage: percentage of expected credits completed
            - progress_status: AHEAD / ON_TRACK / BEHIND
            - is_behind, is_on_track, is_ahead: convenience boolean flags
            - ects_to_graduate: remaining credits needed for 240 ECTS total

        Returns error dict on failure with success=False.
        """
        result = self._progress_service.get_progress(student_id)

        if not result.get("success"):
            return result

        progress = result["progress"]
        completed = progress.get("completed_ects", 0) or 0
        status = progress.get("status", "UNKNOWN")

        # Total ECTS required for graduation (240 is the standard)
        total_required = 240
        ects_to_graduate = max(total_required - completed, 0)

        return {
            "success": True,
            "analytics": {
                "student_id": progress.get("student_id"),
                "student_number": progress.get("student_number"),
                "student_name": progress.get("student_name"),
                "programme": progress.get("programme"),
                "current_semester": progress.get("current_semester"),
                "completed_ects": completed,
                "expected_ects": progress.get("expected_ects", 0),
                "difference_ects": progress.get("difference_ects", 0),
                "remaining_to_expected_ects": progress.get("remaining_to_expected_ects", 0),
                "progress_percentage": progress.get("progress_percentage", 0.0),
                "progress_status": status,
                "is_behind": status == "BEHIND",
                "is_on_track": status == "ON_TRACK",
                "is_ahead": status == "AHEAD",
                "ects_to_graduate": ects_to_graduate,
                "total_required_ects": total_required,
            },
        }

    def calculate_ects_for_cohort(
        self,
        student_ids: list[int],
    ) -> dict[str, Any]:
        """Calculate ECTS progress for a list of students.

        Processes each student individually. Failed lookups are recorded
        in the errors list but do not stop processing of other students.

        Args:
            student_ids: List of numeric student database IDs.

        Returns:
            A dict with:
            - success: True if at least one student was processed
            - results: list of individual analytics dicts for successful lookups
            - errors: list of error dicts for failed lookups
            - summary: cohort-level aggregated statistics
        """
        if not student_ids:
            return {
                "success": False,
                "error": "EMPTY_STUDENT_LIST",
                "message": "No student IDs provided.",
            }

        results = []
        errors = []

        for sid in student_ids:
            result = self.calculate_ects_progress(sid)
            if result.get("success"):
                results.append(result["analytics"])
            else:
                errors.append({
                    "student_id": sid,
                    "error": result.get("error"),
                    "message": result.get("message"),
                })

        summary = _build_cohort_summary(results)

        return {
            "success": len(results) > 0,
            "processed": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
            "summary": summary,
        }


def _build_cohort_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregated cohort statistics from individual analytics results."""
    if not results:
        return {
            "total_students": 0,
            "behind_count": 0,
            "on_track_count": 0,
            "ahead_count": 0,
            "average_completed_ects": 0.0,
            "average_progress_percentage": 0.0,
        }

    total = len(results)
    behind = sum(1 for r in results if r.get("is_behind"))
    on_track = sum(1 for r in results if r.get("is_on_track"))
    ahead = sum(1 for r in results if r.get("is_ahead"))

    avg_ects = sum(r.get("completed_ects", 0) for r in results) / total
    avg_pct = sum(r.get("progress_percentage", 0.0) for r in results) / total

    return {
        "total_students": total,
        "behind_count": behind,
        "on_track_count": on_track,
        "ahead_count": ahead,
        "average_completed_ects": round(avg_ects, 2),
        "average_progress_percentage": round(avg_pct, 2),
    }
