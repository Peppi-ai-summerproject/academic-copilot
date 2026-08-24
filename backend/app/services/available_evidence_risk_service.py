"""Interactive-policy risk assessment for synchronous autonomous workflows."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.risk_policy import (
    event_risk_factors,
    highest_risk_level,
    progress_risk_factors,
    study_right_risk_factors,
)


class AvailableEvidenceRiskService:
    """Preserve verified risk factors when independent dimensions are unavailable.

    This is the synchronous counterpart of ``RiskDetectionAgent`` for workflows
    that cannot invoke the async agent graph. It uses the same risk-policy
    functions and never substitutes missing academic facts.
    """

    def __init__(
        self,
        *,
        progress_provider: Any,
        study_right_provider: Any,
        event_provider: Any,
        tutor_meeting_provider: Any | None = None,
    ) -> None:
        self._progress = progress_provider
        self._study_right = study_right_provider
        self._events = event_provider
        self._tutor_meetings = tutor_meeting_provider

    def assess_student_risk(self, student_id: int, *, as_of_date: date) -> dict[str, Any]:
        factors: list[dict[str, Any]] = []
        unavailable: list[str] = []

        progress = self._safe_call(self._progress.get_progress, student_id)
        progress_value = progress.get("progress") if isinstance(progress, dict) else None
        if isinstance(progress_value, dict) and progress.get("success") is True:
            factors.extend(progress_risk_factors(progress_value))
        else:
            unavailable.append("progress")

        study_right = self._safe_call(self._study_right.get_study_right, student_id)
        study_value = (
            study_right.get("study_right") if isinstance(study_right, dict) else None
        )
        if isinstance(study_value, dict) and study_right.get("success") is True:
            factors.extend(study_right_risk_factors(study_value))
        else:
            unavailable.append("study_right")

        events = self._safe_call(
            self._events.get_upcoming_events,
            start_date=as_of_date.isoformat(),
            end_date=None,
        )
        event_values = events.get("events") if isinstance(events, dict) else None
        if isinstance(event_values, list) and events.get("success") is True:
            event_factors, malformed = event_risk_factors(
                event_values, today=as_of_date
            )
            factors.extend(event_factors)
            if malformed:
                unavailable.append("academic_events")
        else:
            unavailable.append("academic_events")

        tutor = (
            self._safe_call(
                self._tutor_meetings.evaluate_student,
                student_id,
                as_of_date=as_of_date,
            )
            if self._tutor_meetings is not None
            else None
        )
        if not isinstance(tutor, dict) or tutor.get("evaluation_status") != "EVALUATED":
            unavailable.append("tutor_meetings")

        if not factors and "progress" in unavailable:
            return {
                "success": False,
                "assessment_status": "UNAVAILABLE",
                "risk_level": None,
                "risk_factors": [],
                "unavailable_dimensions": unavailable,
            }

        return {
            "success": True,
            "assessment_status": "PARTIAL" if unavailable else "COMPLETE",
            "risk_level": highest_risk_level(factors),
            "risk_factors": factors,
            "unavailable_dimensions": unavailable,
        }

    @staticmethod
    def _safe_call(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except Exception:
            return None
