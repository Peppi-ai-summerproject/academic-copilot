"""Deterministic Academic Health Score derived from canonical risk evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Protocol

from app.services.academic_risk_scoring_service import (
    INDICATOR_ORDER,
    MAXIMUM_POINTS,
    SUPPORTED_OVERRIDE_CODES,
)


POLICY_VERSION = "academic-health-v1"
SCORE_RANGE = {"minimum": 0, "maximum": 100}
SCORE_DIRECTION = "HIGHER_IS_HEALTHIER"


class AcademicRiskProvider(Protocol):
    def assess_student_risk(
        self, student_id: int, *, as_of_date: date,
        allow_partial_risk_level: bool = False,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HealthComponent:
    indicator_code: str
    maximum_points: int
    health_points: int
    risk_points: int
    matched_rule_code: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_academic_health(risk_assessment: Any) -> dict[str, Any]:
    """Translate a canonical Issue #95 assessment without rescoring evidence."""
    if not isinstance(risk_assessment, dict) or risk_assessment.get("success") is not True:
        return _unprocessable("RISK_ASSESSMENT_UNAVAILABLE")
    student_id = risk_assessment.get("student_id")
    status = risk_assessment.get("assessment_status")
    contributions = risk_assessment.get("indicator_contributions")
    unavailable = risk_assessment.get("unavailable_indicators")
    if (
        not _valid_student_id(student_id)
        or status not in {"COMPLETE", "PARTIAL"}
        or not isinstance(contributions, list)
        or not isinstance(unavailable, list)
        or not all(isinstance(item, str) and item for item in unavailable)
    ):
        return _unprocessable("RISK_ASSESSMENT_MALFORMED", student_id)

    components: list[HealthComponent] = []
    for value in contributions:
        component = _parse_component(value)
        if component is None:
            return _unprocessable("RISK_ASSESSMENT_MALFORMED", student_id)
        components.append(component)
    component_codes = [item.indicator_code for item in components]
    expected_codes = set(INDICATOR_ORDER)
    if (
        len(component_codes) != len(set(component_codes))
        or any(code not in INDICATOR_ORDER for code in component_codes)
        or len(unavailable) != len(set(unavailable))
        or any(code not in INDICATOR_ORDER for code in unavailable)
        or set(component_codes).intersection(unavailable)
        or set(component_codes).union(unavailable) != expected_codes
        or (status == "COMPLETE" and tuple(component_codes) != INDICATOR_ORDER)
    ):
        return _unprocessable("RISK_ASSESSMENT_MALFORMED", student_id)
    available_maximum = sum(item.maximum_points for item in components)
    base_health_points = sum(item.health_points for item in components)
    adjustments = _parse_adjustments(risk_assessment.get("applied_overrides"))
    if adjustments is None:
        return _unprocessable("RISK_ASSESSMENT_MALFORMED", student_id)

    health_score: int | None = None
    health_level: str | None = None
    if status == "COMPLETE":
        risk_score = risk_assessment.get("score")
        if unavailable or available_maximum != 100 or not _valid_score(risk_score):
            return _unprocessable("RISK_ASSESSMENT_MALFORMED", student_id)
        health_score = 100 - risk_score
        adjustment_total = sum(item["health_point_adjustment"] for item in adjustments)
        if base_health_points + adjustment_total != health_score:
            return _unprocessable("RISK_ASSESSMENT_MALFORMED", student_id)
        health_level = classify_health_score(health_score)
    elif not unavailable:
        return _unprocessable("RISK_ASSESSMENT_MALFORMED", student_id)

    summary = (
        f"Academic health is {health_level.lower().replace('_', ' ')} at {health_score}/100."
        if health_score is not None and health_level is not None
        else "Academic health is partial because required indicators are unavailable."
    )
    return {
        "success": True,
        "student_id": student_id,
        "assessment_status": status,
        "health_score": health_score,
        "health_level": health_level,
        "score_range": dict(SCORE_RANGE),
        "score_direction": SCORE_DIRECTION,
        "available_component_maximum": available_maximum,
        "components": [item.to_dict() for item in components],
        "missing_indicators": list(unavailable),
        "adjustments": adjustments,
        "summary": summary,
        "policy_version": POLICY_VERSION,
        "source_risk_policy_version": risk_assessment.get("policy_version"),
    }


class AcademicHealthScoreService:
    def __init__(self, risk_service: AcademicRiskProvider) -> None:
        self._risk_service = risk_service

    def assess_student_health(self, student_id: int, *, as_of_date: date) -> dict[str, Any]:
        if not _valid_student_id(student_id):
            return _unprocessable("INVALID_STUDENT_ID", student_id)
        if not isinstance(as_of_date, date):
            return _unprocessable("INVALID_AS_OF_DATE", student_id)
        try:
            risk = self._risk_service.assess_student_risk(
                student_id, as_of_date=as_of_date, allow_partial_risk_level=False
            )
        except Exception:
            risk = {"success": False, "error": "RISK_SERVICE_FAILURE"}
        return self.convert_risk_assessment(risk)

    def convert_risk_assessment(self, risk_assessment: dict[str, Any]) -> dict[str, Any]:
        """Convert one trusted canonical assessment without evaluating it again."""
        return calculate_academic_health(risk_assessment)


def _parse_component(value: Any) -> HealthComponent | None:
    if not isinstance(value, dict):
        return None
    code, maximum = value.get("indicator_code"), value.get("maximum_points")
    risk_points, rule = value.get("assigned_points"), value.get("matched_rule_code")
    if (
        not isinstance(code, str) or not code or not _nonnegative_int(maximum)
        or maximum != MAXIMUM_POINTS.get(code)
        or not _nonnegative_int(risk_points) or risk_points > maximum
        or not isinstance(rule, str) or not rule
    ):
        return None
    health_points = maximum - risk_points
    return HealthComponent(
        code, maximum, health_points, risk_points, rule,
        f"{code} contributes {health_points} of {maximum} available health points and {risk_points} risk points.",
    )


def _parse_adjustments(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    parsed = []
    for item in value:
        if not isinstance(item, dict):
            return None
        code, raw, adjusted = item.get("code"), item.get("raw_subtotal"), item.get("adjusted_score")
        if (
            code not in SUPPORTED_OVERRIDE_CODES
            or not _valid_score(raw)
            or not _valid_score(adjusted)
            or adjusted < raw
        ):
            return None
        parsed.append({
            "code": code,
            "health_point_adjustment": raw - adjusted,
            "explanation": f"{code} reduces health by {adjusted - raw} additional points to preserve the canonical risk override.",
        })
    return parsed


def classify_health_score(score: int) -> str:
    if score <= 30:
        return "URGENT_SUPPORT"
    if score <= 60:
        return "NEEDS_ATTENTION"
    if score <= 80:
        return "STABLE"
    return "STRONG"


def _unprocessable(code: str, student_id: Any = None) -> dict[str, Any]:
    return {
        "success": False, "student_id": student_id,
        "assessment_status": "UNPROCESSABLE", "health_score": None,
        "health_level": None, "components": [], "missing_indicators": [code],
        "adjustments": [], "summary": f"Academic health could not be evaluated: {code}.",
        "policy_version": POLICY_VERSION,
    }


def _valid_student_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_score(value: Any) -> bool:
    return _nonnegative_int(value) and value <= 100


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
