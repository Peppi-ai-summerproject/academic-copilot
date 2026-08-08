"""Deterministic recommendation decisions from structured academic evidence.

The engine owns recommendation mapping only.  It does not retrieve student
data, calculate academic facts or risk, query RAG, or format tutor-facing
language.  Callers adapt authoritative analytics into ``RecommendationInput``
and may enrich the returned decisions with policy context afterwards.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping


AssessmentStatus = Literal["COMPLETE", "PARTIAL"]


@dataclass(frozen=True)
class RecommendationEvidence:
    """One structured input fact and its provenance."""

    source: str
    reason: str
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupportingEvidence:
    """Optional supporting result produced by an existing analytics agent."""

    source: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"source_agent": self.source, "data": dict(self.data)}


@dataclass(frozen=True)
class RecommendationInput:
    """Normalized recommendation input; all academic facts are pre-calculated."""

    student_id: int | None
    risk_level: str | None
    risk_factors: tuple[dict[str, Any], ...]
    assessment_status: AssessmentStatus
    unavailable_dimensions: tuple[str, ...] = ()
    supporting_evidence: Mapping[str, SupportingEvidence] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationDecision:
    """A testable recommendation decision before optional RAG enrichment."""

    recommendation_type: str
    priority: str
    action: str
    reason_codes: tuple[str, ...]
    evidence: tuple[RecommendationEvidence | SupportingEvidence, ...]
    source_agents: tuple[str, ...]
    policy_query: str

    def to_dict(self) -> dict[str, Any]:
        student_evidence = []
        for item in self.evidence:
            if isinstance(item, SupportingEvidence):
                student_evidence.append(item.to_dict())
            else:
                student_evidence.append({
                    "source_agent": item.source,
                    "reason": item.reason,
                    "values": dict(item.values),
                })
        return {
            "recommendation_type": self.recommendation_type,
            # ``category`` remains for the existing RecommendationAgent contract.
            "category": self.recommendation_type,
            "priority": self.priority,
            "action": self.action,
            "reason_codes": list(self.reason_codes),
            "student_evidence": student_evidence,
            "source_agents": list(self.source_agents),
        }


@dataclass(frozen=True)
class RecommendationAssessment:
    student_id: int | None
    data_status: AssessmentStatus
    decisions: tuple[RecommendationDecision, ...] = ()
    unavailable_dimensions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.data_status == "COMPLETE" and not self.missing_information


@dataclass(frozen=True)
class _Rule:
    recommendation_type: str
    action: str
    reason_code: str
    policy_query: str
    minimum_priority: str | None = None


_PRIORITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_RULES: dict[str, tuple[_Rule, ...]] = {
    "progress": (
        _Rule(
            "progress",
            "Review the student's study plan.",
            "PROGRESS_REVIEW_STUDY_PLAN",
            "academic progress deficit tutor support policy",
        ),
        _Rule(
            "progress",
            "Schedule a tutor meeting.",
            "PROGRESS_SCHEDULE_TUTOR_MEETING",
            "academic progress deficit tutor support policy",
            minimum_priority="MEDIUM",
        ),
    ),
    "study_right": (
        _Rule(
            "study_right",
            "Check study-right extension/support options.",
            "STUDY_RIGHT_REVIEW_SUPPORT_OPTIONS",
            "expiring study right extension support policy",
        ),
    ),
    "academic_event": (
        _Rule(
            "deadline",
            "Review the upcoming academic deadline with the student and agree "
            "on the required next step.",
            "ACADEMIC_DEADLINE_REVIEW_NEXT_STEP",
            "upcoming academic deadline tutor guidance",
        ),
    ),
}


class RecommendationEngine:
    """Map authoritative risk factors to explainable advisory decisions."""

    def evaluate(self, value: RecommendationInput) -> RecommendationAssessment:
        decisions: list[RecommendationDecision] = []
        missing: list[str] = []

        for factor in value.risk_factors:
            if not isinstance(factor, dict):
                missing.append("Malformed risk factor could not be mapped.")
                continue
            dimension = str(factor.get("dimension", ""))
            priority = str(factor.get("level", "LOW")).upper()
            rules = _RULES.get(dimension)
            if not rules:
                missing.append(
                    f"No approved recommendation mapping for risk factor '{dimension}'."
                )
                continue
            if priority not in _PRIORITY_ORDER:
                missing.append(
                    f"Unsupported priority '{priority}' for risk factor '{dimension}'."
                )
                continue

            primary = RecommendationEvidence(
                source="risk",
                reason=str(factor.get("reason") or "Confirmed academic risk factor."),
                values=dict(factor.get("values") or {}),
            )
            supporting = value.supporting_evidence.get(dimension)
            evidence: tuple[RecommendationEvidence | SupportingEvidence, ...] = (
                (primary, supporting) if supporting is not None else (primary,)
            )
            source_agents = tuple(item.source for item in evidence)

            for rule in rules:
                if rule.minimum_priority is not None and (
                    _PRIORITY_ORDER[priority]
                    < _PRIORITY_ORDER[rule.minimum_priority]
                ):
                    continue
                decisions.append(
                    RecommendationDecision(
                        recommendation_type=rule.recommendation_type,
                        priority=priority,
                        action=rule.action,
                        reason_codes=(rule.reason_code,),
                        evidence=evidence,
                        source_agents=source_agents,
                        policy_query=rule.policy_query,
                    )
                )

        return RecommendationAssessment(
            student_id=value.student_id,
            data_status=value.assessment_status,
            decisions=tuple(decisions),
            unavailable_dimensions=tuple(value.unavailable_dimensions),
            missing_information=tuple(missing),
        )
