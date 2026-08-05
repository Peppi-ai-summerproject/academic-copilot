"""Deterministic Academic Risk Scoring Model — Issue #95.

The pure ``calculate_academic_risk`` function consumes structured results from
Issues #93 and #94.  It never recalculates progress or study-right expiry.
``AcademicRiskScoringService`` is a thin orchestrator around those authoritative
services and the existing academic-event service.

Tutor-meeting evidence is supplied by the dedicated deterministic meeting-risk
service. This module validates its normalized contract but does not duplicate
its status, history, or window policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Protocol


POLICY_VERSION = "academic-risk-v1"
SCORE_RANGE = {"minimum": 0, "maximum": 100}
SCORE_DIRECTION = "HIGHER_IS_HIGHER_RISK"

_INDICATOR_ORDER = ("academic_delay", "study_right", "tutor_meetings", "academic_events")
_MAXIMUM_POINTS = {
    "academic_delay": 50,
    "study_right": 30,
    "tutor_meetings": 10,
    "academic_events": 10,
}


class DelayDetector(Protocol):
    def detect_student_delay(self, student_id: int) -> dict[str, Any]: ...


class StudyRightRiskDetector(Protocol):
    def detect_study_right_risk(
        self, student_id: int, as_of_date: date | None = None
    ) -> dict[str, Any]: ...


class AcademicEventProvider(Protocol):
    def get_upcoming_events(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]: ...


class TutorMeetingEvaluator(Protocol):
    def evaluate_student(
        self, student_id: int, *, as_of_date: date
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class IndicatorContribution:
    """Serializable explanation of one verified indicator contribution."""

    indicator_code: str
    authoritative_source: str
    normalized_input: dict[str, Any]
    matched_rule_code: str
    assigned_points: int
    maximum_points: int
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_academic_risk(
    *,
    student_id: int,
    as_of_date: date,
    delay_result: dict[str, Any],
    study_right_result: dict[str, Any],
    academic_events_result: dict[str, Any] | None,
    tutor_meeting_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate an explainable risk result from authoritative evidence.

    ``tutor_meeting_evaluation`` is the normalized result from the dedicated
    tutor-meeting risk service.
    """
    base = _base_result(student_id, as_of_date)
    if not isinstance(student_id, int) or isinstance(student_id, bool) or student_id <= 0:
        return _unprocessable(base, ["INVALID_STUDENT_ID"])
    if not isinstance(as_of_date, date):
        return _unprocessable(base, ["INVALID_AS_OF_DATE"])

    delay = _evaluate_delay(delay_result, student_id)
    if isinstance(delay, str):
        return _unprocessable(base, [delay])
    study_right = _evaluate_study_right(study_right_result, student_id)
    if isinstance(study_right, str):
        return _unprocessable(base, [study_right])

    contributions: list[IndicatorContribution] = [delay, study_right]
    unavailable: list[str] = []

    tutor = _evaluate_tutor_meetings(tutor_meeting_evaluation)
    if isinstance(tutor, IndicatorContribution):
        contributions.append(tutor)
    else:
        unavailable.append("tutor_meetings")

    events = _evaluate_academic_events(academic_events_result, as_of_date)
    if isinstance(events, IndicatorContribution):
        contributions.append(events)
    else:
        unavailable.append("academic_events")

    contributions.sort(key=lambda item: _INDICATOR_ORDER.index(item.indicator_code))
    raw_subtotal = sum(item.assigned_points for item in contributions)
    applied_overrides: list[dict[str, Any]] = []
    adjusted_score = raw_subtotal
    if study_right.matched_rule_code == "STUDY_RIGHT_EXPIRED":
        adjusted_score = max(raw_subtotal, 70)
        applied_overrides.append({
            "code": "STUDY_RIGHT_EXPIRED",
            "minimum_score": 70,
            "raw_subtotal": raw_subtotal,
            "adjusted_score": adjusted_score,
            "explanation": "Expired study right applies a minimum final score of 70.",
        })

    result = {
        **base,
        "success": True,
        "assessment_status": "PARTIAL" if unavailable else "COMPLETE",
        "score": None if unavailable else adjusted_score,
        "raw_subtotal": raw_subtotal,
        "risk_level": None if unavailable else _classify_score(adjusted_score),
        "indicator_contributions": [item.to_dict() for item in contributions],
        "unavailable_indicators": unavailable,
        "applied_overrides": applied_overrides,
        "explanation": _build_explanation(contributions, unavailable, applied_overrides),
    }
    return result


class AcademicRiskScoringService:
    """Orchestrate Issue #95 over authoritative #93/#94 service contracts."""

    def __init__(
        self,
        delay_service: DelayDetector,
        study_right_risk_service: StudyRightRiskDetector,
        event_service: AcademicEventProvider,
        tutor_meeting_risk_service: TutorMeetingEvaluator,
    ) -> None:
        self._delay_service = delay_service
        self._study_right_risk_service = study_right_risk_service
        self._event_service = event_service
        self._tutor_meeting_risk_service = tutor_meeting_risk_service

    def assess_student_risk(self, student_id: int, *, as_of_date: date) -> dict[str, Any]:
        if not isinstance(student_id, int) or isinstance(student_id, bool) or student_id <= 0:
            return _unprocessable(_base_result(student_id, as_of_date), ["INVALID_STUDENT_ID"])
        if not isinstance(as_of_date, date):
            return _unprocessable(_base_result(student_id, as_of_date), ["INVALID_AS_OF_DATE"])

        try:
            delay_result = self._delay_service.detect_student_delay(student_id)
        except Exception:
            delay_result = {"success": False, "error": "DELAY_SERVICE_FAILURE"}
        try:
            study_right_result = self._study_right_risk_service.detect_study_right_risk(
                student_id, as_of_date=as_of_date
            )
        except Exception:
            study_right_result = {"success": False, "error": "STUDY_RIGHT_SERVICE_FAILURE"}
        try:
            events_result = self._event_service.get_upcoming_events(
                start_date=as_of_date.isoformat(),
                end_date=None,
            )
        except Exception:
            events_result = {"success": False, "error": "EVENT_SERVICE_FAILURE"}
        try:
            tutor_result = self._tutor_meeting_risk_service.evaluate_student(
                student_id, as_of_date=as_of_date
            )
        except Exception:
            tutor_result = {
                "success": False,
                "evaluation_status": "UNAVAILABLE",
                "matched_rule_code": "TUTOR_MEETING_EVIDENCE_UNAVAILABLE",
            }

        return calculate_academic_risk(
            student_id=student_id,
            as_of_date=as_of_date,
            delay_result=delay_result,
            study_right_result=study_right_result,
            academic_events_result=events_result,
            tutor_meeting_evaluation=tutor_result,
        )


def _evaluate_delay(result: Any, student_id: int) -> IndicatorContribution | str:
    if not isinstance(result, dict) or result.get("success") is not True:
        return "ACADEMIC_DELAY_UNAVAILABLE"
    value = result.get("delay")
    if not isinstance(value, dict):
        return "ACADEMIC_DELAY_MALFORMED"
    if value.get("student_id") != student_id:
        return "ACADEMIC_DELAY_STUDENT_MISMATCH"
    is_delayed = value.get("is_delayed")
    delay_ects = value.get("delay_ects")
    if not isinstance(is_delayed, bool) or not _is_nonnegative_number(delay_ects):
        return "ACADEMIC_DELAY_MALFORMED"
    if (not is_delayed and delay_ects > 0) or (is_delayed and delay_ects <= 0):
        return "ACADEMIC_DELAY_CONTRADICTORY"

    if delay_ects == 0:
        points, code = 0, "DELAY_NONE"
    elif delay_ects < 30:
        points, code = 15, "DELAY_1_TO_29"
    elif delay_ects < 60:
        points, code = 30, "DELAY_30_TO_59"
    else:
        points, code = 50, "DELAY_60_OR_MORE"
    return IndicatorContribution(
        "academic_delay", "Issue #93 DelayDetectionService",
        {"is_delayed": is_delayed, "delay_ects": delay_ects}, code, points, 50,
        f"Verified academic delay contributes {points} points.",
    )


def _evaluate_study_right(result: Any, student_id: int) -> IndicatorContribution | str:
    if not isinstance(result, dict) or result.get("success") is not True:
        return "STUDY_RIGHT_RISK_UNAVAILABLE"
    value = result.get("risk")
    if not isinstance(value, dict):
        return "STUDY_RIGHT_RISK_MALFORMED"
    if value.get("student_id") != student_id:
        return "STUDY_RIGHT_RISK_STUDENT_MISMATCH"
    status = value.get("risk_status")
    attention = value.get("requires_attention")
    mapping = {
        "SAFE": (0, "STUDY_RIGHT_SAFE", False),
        "EXTENDED": (0, "STUDY_RIGHT_EXTENDED", True),
        "EXPIRING_SOON": (20, "STUDY_RIGHT_EXPIRING_SOON", True),
        "EXPIRED": (30, "STUDY_RIGHT_EXPIRED", True),
    }
    if status not in mapping or not isinstance(attention, bool):
        return "STUDY_RIGHT_RISK_UNSUPPORTED"
    points, code, expected_attention = mapping[status]
    if attention is not expected_attention:
        return "STUDY_RIGHT_RISK_CONTRADICTORY"
    return IndicatorContribution(
        "study_right", "Issue #94 StudyRightRiskService",
        {"risk_status": status, "requires_attention": attention}, code, points, 30,
        f"Verified study-right status {status} contributes {points} points.",
    )


def _evaluate_tutor_meetings(value: Any) -> IndicatorContribution | None:
    """Validate the dedicated evaluator's approved normalized contract."""
    if not isinstance(value, dict) or value.get("success") is not True:
        return None
    if value.get("evaluation_status") != "EVALUATED":
        return None
    points = value.get("assigned_points")
    rule = value.get("matched_rule_code")
    normalized = value.get("normalized_input")
    approved = {
        "RECENT_TUTOR_MEETING_COMPLETED": (0, "COMPLETED"),
        "TUTOR_MEETING_UPCOMING_WITHOUT_RECENT_COMPLETION": (5, "SCHEDULED"),
        "TUTOR_MEETING_MISSED": (10, "MISSED"),
    }
    if not isinstance(points, int) or isinstance(points, bool):
        return None
    if rule not in approved or not isinstance(normalized, dict):
        return None
    expected_points, expected_status = approved[rule]
    required = {
        "meeting_id", "meeting_status", "scheduled_at",
        "lookback_start", "upcoming_end",
    }
    if not required.issubset(normalized) or points != expected_points:
        return None
    meeting_id = normalized["meeting_id"]
    if not isinstance(meeting_id, int) or isinstance(meeting_id, bool) or meeting_id <= 0:
        return None
    if normalized["meeting_status"] != expected_status:
        return None
    if _parse_iso_datetime(normalized["scheduled_at"]) is None:
        return None
    if _parse_iso_date(normalized["lookback_start"]) is None:
        return None
    if _parse_iso_date(normalized["upcoming_end"]) is None:
        return None
    safe_normalized = {
        key: normalized[key]
        for key in (
            "meeting_id", "meeting_status", "scheduled_at",
            "lookback_start", "upcoming_end",
        )
        if key in normalized
    }
    return IndicatorContribution(
        "tutor_meetings", "TutorMeetingRiskService / TutorMeetingRepository",
        safe_normalized, rule, points, 10,
        f"Verified tutor-meeting evidence contributes {points} points.",
    )


def _evaluate_academic_events(result: Any, as_of_date: date) -> IndicatorContribution | None:
    if not isinstance(result, dict) or result.get("success") is not True:
        return None
    events = result.get("events")
    if not isinstance(events, list):
        return None
    applicable: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            return None
        event_type = event.get("event_type")
        event_date = _parse_iso_date(event.get("event_date"))
        applicability = event.get("affects_all_students")
        if not isinstance(event_type, str) or event_date is None or not isinstance(applicability, bool):
            return None
        days_until = (event_date - as_of_date).days
        if event_type.upper() == "DEADLINE" and applicability is True and 0 <= days_until <= 14:
            applicable.append({
                "event_id": event.get("id"),
                "event_date": event_date.isoformat(),
                "days_until_event": days_until,
                "affects_all_students": True,
            })
    points = 10 if applicable else 0
    code = "APPLICABLE_DEADLINE_WITHIN_14_DAYS" if applicable else "NO_APPLICABLE_DEADLINE_WITHIN_14_DAYS"
    return IndicatorContribution(
        "academic_events", "EventService / EventRepository",
        {"applicable_deadlines": applicable, "applicable_deadline_count": len(applicable)},
        code, points, 10,
        f"{len(applicable)} applicable deadline(s) in the inclusive 0–14 day "
        f"window contribute {points} points.",
    )


def _base_result(student_id: Any, as_of_date: Any) -> dict[str, Any]:
    return {
        "success": False,
        "student_id": student_id,
        "as_of_date": as_of_date.isoformat() if isinstance(as_of_date, date) else None,
        "assessment_status": "UNPROCESSABLE",
        "score": None,
        "raw_subtotal": None,
        "score_range": dict(SCORE_RANGE),
        "score_direction": SCORE_DIRECTION,
        "risk_level": None,
        "indicator_contributions": [],
        "unavailable_indicators": [],
        "applied_overrides": [],
        "explanation": [],
        "policy_version": POLICY_VERSION,
    }


def _unprocessable(base: dict[str, Any], codes: list[str]) -> dict[str, Any]:
    return {
        **base,
        "unavailable_indicators": codes,
        "explanation": [f"Assessment is unprocessable: {code}." for code in codes],
    }


def _classify_score(score: int) -> str:
    if score <= 19:
        return "LOW"
    if score <= 39:
        return "MEDIUM"
    if score <= 69:
        return "HIGH"
    return "CRITICAL"


def _build_explanation(
    contributions: list[IndicatorContribution],
    unavailable: list[str],
    overrides: list[dict[str, Any]],
) -> list[str]:
    messages = [item.explanation for item in contributions]
    messages.extend(f"{code} could not be authoritatively evaluated." for code in unavailable)
    messages.extend(item["explanation"] for item in overrides)
    if unavailable:
        messages.append("The verified subtotal is not an overall risk score or classification.")
    return messages


def _is_nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
