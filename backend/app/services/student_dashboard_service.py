"""Dashboard service that aggregates multiple student data sources."""

from datetime import date
from typing import Any, Protocol

from app.repositories.student_repository import StudentRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.event_repository import EventRepository
from app.services.student_service import StudentService
from app.services.progress_service import ProgressService
from app.services.study_right_service import StudyRightService
from app.services.event_service import EventService
from app.services.risk_policy import (
    highest_risk_level,
    progress_risk_factors,
    study_right_risk_factors,
)


class AcademicHealthProvider(Protocol):
    def assess_student_health(
        self, student_id: int, *, as_of_date: date
    ) -> dict[str, Any]: ...

    def convert_risk_assessment(
        self, risk_assessment: dict[str, Any]
    ) -> dict[str, Any]: ...


class AcademicRiskProvider(Protocol):
    def assess_student_risk(
        self, student_id: int, *, as_of_date: date,
        allow_partial_risk_level: bool = False,
    ) -> dict[str, Any]: ...


class StudentDashboardService:
    """Aggregates student data from multiple services into a single dashboard.

    Composes existing services rather than duplicating their business logic.
    Missing optional sections degrade gracefully without failing the whole response.

    Args:
        student_service: Service for retrieving student profile.
        progress_service: Service for calculating academic progress.
        study_right_service: Service for study right status.
        event_service: Service for upcoming academic events.
    """

    def __init__(
        self,
        student_service: StudentService,
        progress_service: ProgressService,
        study_right_service: StudyRightService,
        event_service: EventService,
        academic_health_service: AcademicHealthProvider | None = None,
        academic_risk_service: AcademicRiskProvider | None = None,
    ) -> None:
        self._student_service = student_service
        self._progress_service = progress_service
        self._study_right_service = study_right_service
        self._event_service = event_service
        self._academic_health_service = academic_health_service
        self._academic_risk_service = academic_risk_service

    def get_student_dashboard(
        self,
        student_id: int,
        *,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        """Return a complete student overview for tutor teachers and AI agents.

        Missing optional sections (progress, study right, events) degrade
        gracefully. A missing student record fails the entire request.

        Args:
            student_id: The numeric database ID of the student.

        Returns:
            A JSON-serializable dict with success status and a dashboard
            containing profile, academic_progress, study_right, academic_health, risk,
            upcoming_actions, and summary sections.
        """
        if not isinstance(student_id, int) or student_id <= 0:
            return {
                "success": False,
                "error": "INVALID_STUDENT_ID",
                "message": "Student ID must be a positive integer.",
            }
        if as_of_date is not None and not isinstance(as_of_date, date):
            return {
                "success": False,
                "error": "INVALID_AS_OF_DATE",
                "message": "Assessment date must be a date.",
            }
        effective_date = as_of_date or date.today()

        # ── Student profile (required) ─────────────────────────────────────
        student_result = self._student_service.get_student(student_id)
        if not student_result.get("success"):
            return student_result

        profile = self._build_profile(student_result["student"])

        # ── Academic progress (optional) ───────────────────────────────────
        progress_result = self._progress_service.get_progress(student_id)
        if progress_result.get("success"):
            academic_progress = self._build_progress(progress_result["progress"])
        else:
            academic_progress = {
                "available": False,
                "reason": progress_result.get("error", "PROGRESS_UNAVAILABLE"),
            }

        # ── Study right (optional) ─────────────────────────────────────────
        study_right_result = self._study_right_service.get_study_right(student_id)
        if study_right_result.get("success"):
            study_right = self._build_study_right(study_right_result["study_right"])
        else:
            study_right = {
                "available": False,
                "reason": study_right_result.get("error", "STUDY_RIGHT_UNAVAILABLE"),
            }

        # ── Risk analysis (computed from available data) ───────────────────
        # Canonical overall risk is authoritative; legacy progress/study-right
        # heuristics remain only as explicitly labeled supporting context.
        canonical_risk = self._assess_canonical_risk(student_id, effective_date)
        risk = self._build_risk(academic_progress, study_right, canonical_risk)

        # ── Upcoming academic events (optional) ────────────────────────────
        events_result = self._event_service.get_upcoming_events(
            start_date=effective_date.isoformat(),
            end_date=None,
        )
        if events_result.get("success"):
            upcoming_actions = self._build_upcoming_actions(events_result["events"])
        else:
            upcoming_actions = {
                "academic_events": [],
                "tutor_meetings": [],
                "recommended_actions": [],
            }

        # ── Summary ────────────────────────────────────────────────────────
        academic_health = self._build_academic_health(canonical_risk)
        summary = self._build_summary(academic_progress, study_right, risk)

        return {
            "success": True,
            "student_id": student_id,
            "dashboard": {
                "profile": profile,
                "academic_progress": academic_progress,
                "study_right": study_right,
                "academic_health": academic_health,
                "risk": risk,
                "upcoming_actions": upcoming_actions,
                "summary": summary,
            },
        }

    # ── Private builders ───────────────────────────────────────────────────────

    def _assess_canonical_risk(
        self,
        student_id: int,
        effective_date: date,
    ) -> dict[str, Any] | None:
        if self._academic_risk_service is None:
            return None
        try:
            return self._academic_risk_service.assess_student_risk(
                student_id,
                as_of_date=effective_date,
                allow_partial_risk_level=False,
            )
        except Exception:
            return None

    def _build_academic_health(
        self, canonical_risk: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Call the analytics service; never calculate health in the dashboard."""
        if (
            self._academic_health_service is None
            or not self._is_usable_canonical_risk(canonical_risk)
        ):
            return self._unavailable_health("ACADEMIC_HEALTH_SERVICE_UNAVAILABLE")
        try:
            return self._academic_health_service.convert_risk_assessment(
                canonical_risk
            )
        except Exception:
            return self._unavailable_health("ACADEMIC_HEALTH_SERVICE_FAILURE")

    @staticmethod
    def _unavailable_health(reason: str) -> dict[str, Any]:
        return {
            "success": False,
            "assessment_status": "UNAVAILABLE",
            "health_score": None,
            "health_level": None,
            "components": [],
            "missing_indicators": [reason],
            "summary": "Academic health is unavailable.",
        }

    @staticmethod
    def _is_usable_canonical_risk(value: Any) -> bool:
        return isinstance(value, dict) and value.get("success") is True

    def _build_profile(self, student: dict[str, Any]) -> dict[str, Any]:
        """Map raw student fields to dashboard profile section."""
        return {
            "student_id": student.get("id"),
            "student_number": student.get("student_number"),
            "name": student.get("name"),
            "group_name": student.get("group_name"),
            "programme": student.get("programme"),
            "programme_code": student.get("programme_code"),
            "start_date": (
                student["start_date"].isoformat()
                if hasattr(student.get("start_date"), "isoformat")
                else str(student.get("start_date"))
                if student.get("start_date") is not None
                else None
            ),
            "status": student.get("status"),
        }

    def _build_progress(self, progress: dict[str, Any]) -> dict[str, Any]:
        """Map progress service output to dashboard academic_progress section."""
        return {
            "available": True,
            "student_id": progress.get("student_id"),
            "programme": progress.get("programme"),
            "current_semester": progress.get("current_semester"),
            "completed_ects": progress.get("completed_ects"),
            "expected_ects": progress.get("expected_ects"),
            "difference_ects": progress.get("difference_ects"),
            "remaining_to_expected_ects": progress.get("remaining_to_expected_ects"),
            "progress_percentage": progress.get("progress_percentage"),
            "status": progress.get("status"),
        }

    def _build_study_right(self, study_right: dict[str, Any]) -> dict[str, Any]:
        """Map study right service output to dashboard study_right section."""

        def _date_str(value: Any) -> str | None:
            if value is None:
                return None
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return str(value)

        return {
            "available": True,
            "status": study_right.get("status"),
            "start_date": _date_str(study_right.get("start_date")),
            "end_date": _date_str(study_right.get("end_date")),
            "expiration_date": _date_str(study_right.get("expiration_date")),
            "extension_count": study_right.get("extension_count"),
            "is_expiring_soon": study_right.get("is_expiring_soon", False),
        }

    def _build_risk(
        self,
        academic_progress: dict[str, Any],
        study_right: dict[str, Any],
        canonical_risk: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Present canonical risk and retain labeled legacy supporting context.

        Note: No persisted risk_events table exists in the current backend.
        Risk is computed deterministically from current data.
        Persisted events list is empty until a risk repository is implemented.
        """
        factors: list[dict[str, Any]] = []
        if academic_progress.get("available"):
            factors.extend(progress_risk_factors(academic_progress))
        if study_right.get("available"):
            factors.extend(study_right_risk_factors(study_right))
        legacy_reasons = [factor["reason"] for factor in factors]
        legacy_level = highest_risk_level(factors, default="LOW")

        if not legacy_reasons:
            legacy_reasons.append("No immediate risks detected.")

        canonical_success = self._is_usable_canonical_risk(canonical_risk)
        canonical_level = canonical_risk.get("risk_level") if canonical_success else None
        explanation = canonical_risk.get("explanation") if canonical_success else None
        reasons = (
            list(explanation)
            if isinstance(explanation, list)
            and all(isinstance(item, str) for item in explanation)
            else ["Canonical academic risk is unavailable."]
        )

        return {
            "current_analysis": {
                "risk_level": canonical_level,
                "reasons": reasons,
                "assessment_status": (
                    canonical_risk.get("assessment_status")
                    if canonical_success else "UNAVAILABLE"
                ),
                "score": canonical_risk.get("score") if canonical_success else None,
                "source": (
                    "ACADEMIC_RISK_SCORING_SERVICE"
                    if canonical_success else "LEGACY_PROGRESS_STUDY_RIGHT_FALLBACK"
                ),
            },
            "supporting_legacy_analysis": {
                "scope": "PROGRESS_AND_STUDY_RIGHT_ONLY",
                "source": "LEGACY_PROGRESS_STUDY_RIGHT_HEURISTIC",
                "risk_level": legacy_level,
                "reasons": legacy_reasons,
                "authoritative_overall_risk": False,
            },
            "events": [],  # No persisted risk_events backend yet
        }

    def _build_upcoming_actions(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build upcoming actions from academic events.

        Note: No tutor_meetings backend repository exists yet.
        Academic events are returned as-is. Tutor meetings and
        recommended actions are empty until those repositories exist.
        """
        academic_events = [
            {
                "id": event.get("id"),
                "event_name": event.get("event_name"),
                "event_type": event.get("event_type"),
                "event_date": event.get("event_date"),
                "description": event.get("description"),
                "affects_all_students": event.get("affects_all_students"),
            }
            for event in events
        ]

        return {
            "academic_events": academic_events,
            "tutor_meetings": [],  # No tutor_meetings backend repository yet
            "recommended_actions": [],
        }

    def _build_summary(
        self,
        academic_progress: dict[str, Any],
        study_right: dict[str, Any],
        risk: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a structured summary suitable for AI-generated responses."""
        key_findings: list[str] = []
        attention_required = False

        current_risk = risk["current_analysis"]
        risk_level = current_risk["risk_level"]
        assessment_status = current_risk.get("assessment_status")

        # Progress findings
        if academic_progress.get("available"):
            status = academic_progress.get("status")
            completed = academic_progress.get("completed_ects", 0)
            expected = academic_progress.get("expected_ects", 0)
            if status == "BEHIND":
                key_findings.append(
                    f"Student has completed {completed} ECTS "
                    f"but {expected} ECTS were expected."
                )
                attention_required = True
            elif status == "AHEAD":
                key_findings.append(
                    f"Student is ahead of schedule with {completed} ECTS completed."
                )
            else:
                key_findings.append(
                    f"Student is on track with {completed} ECTS completed."
                )
        else:
            key_findings.append("Academic progress data is unavailable.")

        # Study right findings
        if study_right.get("available"):
            sr_status = study_right.get("status")
            if sr_status == "EXPIRES_SOON":
                key_findings.append(
                    f"Study right is expiring soon "
                    f"({study_right.get('expiration_date')})."
                )
                attention_required = True
            elif sr_status == "EXPIRED":
                key_findings.append("Study right has expired.")
                attention_required = True
            elif sr_status == "EXTENDED":
                key_findings.append(
                    f"Study right has been extended "
                    f"({study_right.get('extension_count', 0)} time(s))."
                )
            else:
                key_findings.append(
                    f"Study right is active until {study_right.get('expiration_date')}."
                )
        else:
            key_findings.append("Study right data is unavailable.")

        # Risk-based priority
        if risk_level in {"CRITICAL", "HIGH"}:
            priority = "HIGH"
            attention_required = True
        elif risk_level == "MEDIUM":
            priority = "MEDIUM"
            attention_required = True
        elif risk_level == "LOW":
            priority = "LOW"
        else:
            priority = "UNKNOWN"
            attention_required = True
            if assessment_status == "PARTIAL":
                key_findings.append(
                    "Academic risk assessment is incomplete; authoritative "
                    "priority is indeterminate."
                )
            elif assessment_status == "UNAVAILABLE":
                key_findings.append(
                    "Academic risk assessment is unavailable; authoritative "
                    "priority is indeterminate."
                )
            else:
                key_findings.append(
                    "Academic risk level is unsupported; authoritative "
                    "priority is indeterminate."
                )

        overall_status = (
            "NEEDS_ATTENTION" if attention_required else "ON_TRACK"
        )

        return {
            "overall_status": overall_status,
            "attention_required": attention_required,
            "priority": priority,
            "key_findings": key_findings,
        }
