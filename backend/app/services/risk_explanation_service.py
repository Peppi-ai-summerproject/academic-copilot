"""Deterministic explanations for existing academic-risk assessments.

Issue #113 deliberately consumes the structured result produced by Issue #95.
It does not accept raw student data and does not calculate, normalize, or
classify risk.  This keeps the academic-risk scorer as the only source of
truth for a student's score and risk level.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any


_ASSESSMENT_STATUSES = frozenset({"COMPLETE", "PARTIAL"})
_RISK_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})


@dataclass(frozen=True)
class RiskExplanationInput:
    """The already-calculated canonical risk result to explain."""

    student_id: int
    risk_result: dict[str, Any]
    source: str = "AcademicRiskScoringService.assess_student_risk"


@dataclass(frozen=True)
class RiskExplanationFactor:
    """One source-backed canonical indicator, ordered by its existing points."""

    indicator_code: str
    contribution: int
    maximum_contribution: int
    matched_rule_code: str
    authoritative_source: str
    evidence: dict[str, Any]
    explanation: str


@dataclass(frozen=True)
class RiskExplanation:
    """Tutor-readable view of a canonical risk assessment."""

    student_id: int
    success: bool
    assessment_status: str
    summary: str
    risk_score: int | None = None
    risk_level: str | None = None
    score_basis: str | None = None
    policy_version: str | None = None
    factors: tuple[RiskExplanationFactor, ...] = ()
    unavailable_indicators: tuple[str, ...] = ()
    applied_overrides: tuple[dict[str, Any], ...] = ()
    source_explanations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return {
            "student_id": self.student_id,
            "success": self.success,
            "assessment_status": self.assessment_status,
            "summary": self.summary,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "score_basis": self.score_basis,
            "policy_version": self.policy_version,
            "factors": [asdict(factor) for factor in self.factors],
            "unavailable_indicators": list(self.unavailable_indicators),
            "applied_overrides": [deepcopy(item) for item in self.applied_overrides],
            "source_explanations": list(self.source_explanations),
            "warnings": list(self.warnings),
        }


class RiskExplanationService:
    """Explain, but never alter, a successful Issue #95 risk result."""

    def explain(self, explanation_input: RiskExplanationInput) -> RiskExplanation:
        """Build an explanation directly from canonical score evidence.

        A malformed or unavailable upstream result is disclosed as
        ``UNPROCESSABLE`` instead of being reconstructed from other services.
        """

        result = explanation_input.risk_result
        student_id = explanation_input.student_id
        if not isinstance(result, dict) or result.get("success") is not True:
            return _unavailable_explanation(
                student_id,
                _result_warning(result, "RISK_ASSESSMENT_UNAVAILABLE"),
            )
        if result.get("student_id") != student_id:
            return _unavailable_explanation(student_id, "RISK_ASSESSMENT_STUDENT_MISMATCH")

        assessment_status = result.get("assessment_status")
        risk_score = result.get("score")
        risk_level = result.get("risk_level")
        score_basis = result.get("score_basis")
        policy_version = result.get("policy_version")
        unavailable = result.get("unavailable_indicators")
        source_explanations = result.get("explanation")
        overrides = result.get("applied_overrides")
        factors = _factors_from(result.get("indicator_contributions"))

        if not _is_valid_assessment(
            assessment_status=assessment_status,
            risk_score=risk_score,
            risk_level=risk_level,
            score_basis=score_basis,
            policy_version=policy_version,
            unavailable=unavailable,
            source_explanations=source_explanations,
            overrides=overrides,
            factors=factors,
        ):
            return _unavailable_explanation(student_id, "CANONICAL_RISK_ASSESSMENT_MALFORMED")

        ordered_factors = tuple(
            factor
            for _, factor in sorted(
                enumerate(factors),
                key=lambda item: (-item[1].contribution, item[0]),
            )
        )
        unavailable_codes = tuple(unavailable)
        copied_overrides = tuple(deepcopy(item) for item in overrides)
        warnings = _warnings(assessment_status, unavailable_codes)

        return RiskExplanation(
            student_id=student_id,
            success=True,
            assessment_status=assessment_status,
            summary=_summary(
                risk_score=risk_score,
                risk_level=risk_level,
                assessment_status=assessment_status,
                score_basis=score_basis,
                factors=ordered_factors,
                unavailable_indicators=unavailable_codes,
                overrides=copied_overrides,
            ),
            risk_score=risk_score,
            risk_level=risk_level,
            score_basis=score_basis,
            policy_version=policy_version,
            factors=ordered_factors,
            unavailable_indicators=unavailable_codes,
            applied_overrides=copied_overrides,
            source_explanations=tuple(source_explanations),
            warnings=warnings,
        )


def _factors_from(value: Any) -> list[RiskExplanationFactor] | None:
    if not isinstance(value, list):
        return None

    factors: list[RiskExplanationFactor] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        indicator_code = item.get("indicator_code")
        contribution = item.get("assigned_points")
        maximum = item.get("maximum_points")
        rule_code = item.get("matched_rule_code")
        source = item.get("authoritative_source")
        evidence = item.get("normalized_input")
        explanation = item.get("explanation")
        if (
            not isinstance(indicator_code, str)
            or not indicator_code
            or not _is_points(contribution)
            or not _is_points(maximum)
            or contribution > maximum
            or not isinstance(rule_code, str)
            or not rule_code
            or not isinstance(source, str)
            or not source
            or not isinstance(evidence, dict)
            or not isinstance(explanation, str)
            or not explanation
        ):
            return None
        factors.append(
            RiskExplanationFactor(
                indicator_code=indicator_code,
                contribution=contribution,
                maximum_contribution=maximum,
                matched_rule_code=rule_code,
                authoritative_source=source,
                evidence=deepcopy(evidence),
                explanation=explanation,
            )
        )
    return factors


def _is_valid_assessment(
    *,
    assessment_status: Any,
    risk_score: Any,
    risk_level: Any,
    score_basis: Any,
    policy_version: Any,
    unavailable: Any,
    source_explanations: Any,
    overrides: Any,
    factors: list[RiskExplanationFactor] | None,
) -> bool:
    if assessment_status not in _ASSESSMENT_STATUSES:
        return False
    if risk_score is not None and not _is_score(risk_score):
        return False
    if risk_level is not None and risk_level not in _RISK_LEVELS:
        return False
    if (risk_score is None) != (risk_level is None):
        return False
    if score_basis is not None and (not isinstance(score_basis, str) or not score_basis):
        return False
    if not isinstance(policy_version, str) or not policy_version:
        return False
    if not isinstance(unavailable, list) or not all(isinstance(item, str) and item for item in unavailable):
        return False
    if not isinstance(source_explanations, list) or not all(
        isinstance(item, str) for item in source_explanations
    ):
        return False
    if not isinstance(overrides, list) or not all(isinstance(item, dict) for item in overrides):
        return False
    return factors is not None


def _summary(
    *,
    risk_score: int | None,
    risk_level: str | None,
    assessment_status: str,
    score_basis: str | None,
    factors: tuple[RiskExplanationFactor, ...],
    unavailable_indicators: tuple[str, ...],
    overrides: tuple[dict[str, Any], ...],
) -> str:
    if risk_score is None or risk_level is None:
        summary = (
            "The canonical assessment is PARTIAL and does not provide a final "
            "risk score or risk level."
        )
    else:
        summary = (
            f"The student is classified as {risk_level} risk with the existing "
            f"canonical score of {risk_score}/100."
        )

    contributors = [factor for factor in factors if factor.contribution > 0]
    if contributors:
        rendered = ", ".join(
            f"{_display_name(factor.indicator_code)} "
            f"({factor.contribution} of {factor.maximum_contribution} points)"
            for factor in contributors
        )
        summary += f" Risk-increasing indicators are {rendered}."
    elif factors:
        summary += " No verified indicator contributed risk points."

    if assessment_status == "PARTIAL":
        rendered_unavailable = ", ".join(
            _display_name(indicator) for indicator in unavailable_indicators
        )
        summary += (
            f" This is a PARTIAL assessment: {rendered_unavailable} was unavailable "
            "and was not treated as zero."
        )
        if score_basis == "available_indicator_weights":
            summary += " The existing score is normalized against available indicator weights."
    else:
        summary += " This is a COMPLETE assessment based on all expected indicators."

    override_codes = [item.get("code") for item in overrides if isinstance(item.get("code"), str)]
    if override_codes:
        summary += f" Canonical override(s) applied: {', '.join(override_codes)}."
    return summary


def _warnings(assessment_status: str, unavailable: tuple[str, ...]) -> tuple[str, ...]:
    if assessment_status != "PARTIAL":
        return ()
    return (
        "Missing indicators are disclosed and were not inferred or treated as zero.",
        *(
            f"Unavailable canonical indicator: {indicator}."
            for indicator in unavailable
        ),
    )


def _unavailable_explanation(student_id: int, warning: str) -> RiskExplanation:
    return RiskExplanation(
        student_id=student_id,
        success=False,
        assessment_status="UNPROCESSABLE",
        summary=(
            "Risk cannot be explained because canonical risk scoring did not "
            "produce a usable assessment."
        ),
        warnings=(warning,),
    )


def _result_warning(result: Any, default: str) -> str:
    if isinstance(result, dict) and isinstance(result.get("error"), str) and result["error"]:
        return result["error"]
    return default


def _is_score(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100


def _is_points(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _display_name(value: str) -> str:
    return value.replace("_", " ")
