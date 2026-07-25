from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.curriculum_service import CurriculumService
from app.services.event_service import EventService
from app.services.progress_service import ProgressService
from app.services.student_service import StudentService
from app.services.study_right_service import StudyRightService


class ReportService:
    """Compose structured academic reports from existing domain services."""

    def __init__(
        self,
        student_service: StudentService,
        progress_service: ProgressService,
        study_right_service: StudyRightService,
        curriculum_service: CurriculumService,
        event_service: EventService,
    ) -> None:
        self._student_service = student_service
        self._progress_service = progress_service
        self._study_right_service = study_right_service
        self._curriculum_service = curriculum_service
        self._event_service = event_service

    def generate_report(
        self,
        student_id: int,
        report_type: str = "academic_summary",
    ) -> dict[str, Any]:
        if report_type != "academic_summary":
            return {
                "success": False,
                "error": "INVALID_REPORT_TYPE",
                "message": (
                    f"Report type '{report_type}' is not supported. "
                    "Only 'academic_summary' is available."
                ),
            }

        student_result = self._student_service.get_student(student_id)

        if not student_result["success"]:
            return student_result

        student = student_result["student"]
        warnings: list[str] = []

        progress_result = self._progress_service.get_progress(student_id)
        progress = self._extract_progress(progress_result, warnings)

        curriculum_result = self._curriculum_service.get_curriculum(
            student["programme"],
        )
        curriculum = self._extract_curriculum(curriculum_result, warnings)

        study_right_result = self._study_right_service.get_study_right(student_id)
        study_right = self._extract_study_right(study_right_result, warnings)

        events_result = self._event_service.get_upcoming_events()
        upcoming_events = self._extract_upcoming_events(events_result, warnings)

        risk_assessment = None
        overall_status = self._determine_overall_status(risk_assessment)
        self._append_warning(
            warnings,
            "Risk assessment is unavailable.",
        )

        summary = {
            "overall_status": overall_status,
            "key_findings": self._build_key_findings(
                progress=progress,
                study_right=study_right,
                curriculum=curriculum,
                upcoming_events=upcoming_events,
            ),
            "recommended_actions": self._build_recommended_actions(
                overall_status=overall_status,
                progress=progress,
                study_right=study_right,
            ),
            "warnings": warnings,
        }

        return {
            "success": True,
            "report": {
                "report_type": report_type,
                "generated_at": self._current_timestamp(),
                "student": student,
                "academic_progress": progress,
                "study_right": study_right,
                "curriculum": curriculum,
                "risk_assessment": risk_assessment,
                "upcoming_events": upcoming_events,
                "summary": summary,
            },
        }

    def _extract_progress(
        self,
        result: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any] | None:
        if result["success"]:
            return result["progress"]

        self._append_warning(warnings, "Academic progress could not be calculated.")

        if result.get("error") == "CURRICULUM_NOT_FOUND":
            self._append_warning(
                warnings,
                "Curriculum information was not found.",
            )

        return None

    def _extract_curriculum(
        self,
        result: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any] | None:
        if result["success"]:
            return result["curriculum"]

        self._append_warning(
            warnings,
            "Curriculum information was not found.",
        )
        return None

    def _extract_study_right(
        self,
        result: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any] | None:
        if result["success"]:
            return result["study_right"]

        self._append_warning(
            warnings,
            "Study right information was not found.",
        )
        return None

    def _extract_upcoming_events(
        self,
        result: dict[str, Any],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        if result["success"]:
            return result["events"]

        self._append_warning(
            warnings,
            "Upcoming events could not be retrieved.",
        )
        return []

    @staticmethod
    def _append_warning(
        warnings: list[str],
        message: str,
    ) -> None:
        if message not in warnings:
            warnings.append(message)

    def _determine_overall_status(
        self,
        risk_assessment: dict[str, Any] | None,
    ) -> str:
        if risk_assessment is None:
            return "UNKNOWN"

        risk_level = str(risk_assessment.get("risk_level", "")).upper()

        if risk_level == "HIGH":
            return "HIGH_RISK"

        if risk_level == "MEDIUM":
            return "NEEDS_ATTENTION"

        return "ON_TRACK"

    def _build_key_findings(
        self,
        progress: dict[str, Any] | None,
        study_right: dict[str, Any] | None,
        curriculum: dict[str, Any] | None,
        upcoming_events: list[dict[str, Any]],
    ) -> list[str]:
        findings: list[str] = []

        if progress is not None:
            status = progress.get("status")
            difference_ects = progress.get("difference_ects")

            if status == "BEHIND":
                findings.append(
                    f"Student is behind expected progress by {abs(difference_ects)} ECTS."
                )
            elif status == "ON_TRACK":
                findings.append(
                    "Student is progressing according to curriculum expectations."
                )
            elif status == "AHEAD":
                findings.append(
                    f"Student is ahead of expected progress by {difference_ects} ECTS."
                )

        if study_right is not None and study_right.get("is_expiring_soon"):
            findings.append("Study right expires soon.")

        if curriculum is None:
            findings.append("Curriculum information was not found.")

        if not upcoming_events:
            findings.append("No upcoming academic events were found.")

        findings.append("Risk assessment is unavailable.")

        return findings

    def _build_recommended_actions(
        self,
        overall_status: str,
        progress: dict[str, Any] | None,
        study_right: dict[str, Any] | None,
    ) -> list[str]:
        if overall_status == "HIGH_RISK":
            return [
                "Schedule a tutor meeting.",
                "Review the student's study plan.",
                "Check whether study-right extension support is required.",
            ]

        if overall_status == "NEEDS_ATTENTION":
            return [
                "Review recent academic progress.",
                "Discuss upcoming course completion plans.",
            ]

        return [
            "Review available student information and follow up as needed.",
            "Continue monitoring progress during the next tutor meeting.",
        ]

    @staticmethod
    def _current_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()