"""Deterministic tutor interventions derived from recommendation decisions.

This service consumes Issue #110 recommendation decisions.  It never reads
student data, recalculates analytics or risk, retrieves policy, or calls an
LLM.  Its only responsibilities are intervention classification, priority
preservation, deduplication, ordering, and evidence preservation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.recommendation_engine import (
    AssessmentStatus,
    RecommendationDecision,
    RecommendationEvidence,
    SupportingEvidence,
)


InterventionType = Literal[
    "MONITOR_PROGRESS",
    "REVIEW_STUDY_PLAN",
    "SCHEDULE_TUTOR_MEETING",
    "REVIEW_STUDY_RIGHT",
    "REVIEW_ACADEMIC_DEADLINE",
]


@dataclass(frozen=True)
class InterventionInput:
    """Recommendation output adapted for intervention selection."""

    student_id: int | None
    data_status: AssessmentStatus
    recommendation_decisions: tuple[RecommendationDecision, ...]
    unavailable_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class InterventionSuggestion:
    """One concrete tutor action with its originating decision evidence."""

    intervention_type: InterventionType
    priority: str
    action: str
    reason_codes: tuple[str, ...]
    evidence: tuple[RecommendationEvidence | SupportingEvidence, ...]
    source_agents: tuple[str, ...]
    policy_query: str

    def to_dict(self) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        for item in self.evidence:
            if isinstance(item, SupportingEvidence):
                evidence.append(item.to_dict())
            else:
                evidence.append({
                    "source_agent": item.source,
                    "reason": item.reason,
                    "values": dict(item.values),
                })
        return {
            "intervention_type": self.intervention_type,
            "priority": self.priority,
            "action": self.action,
            "reason_codes": list(self.reason_codes),
            "student_evidence": evidence,
            "source_agents": list(self.source_agents),
        }


@dataclass(frozen=True)
class InterventionAssessment:
    student_id: int | None
    data_status: AssessmentStatus
    suggestions: tuple[InterventionSuggestion, ...] = ()
    unavailable_dimensions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.data_status == "COMPLETE" and not self.missing_information


_INTERVENTION_BY_REASON: dict[str, InterventionType] = {
    "NO_CONFIRMED_RISK_CONTINUE_MONITORING": "MONITOR_PROGRESS",
    "PROGRESS_REVIEW_STUDY_PLAN": "REVIEW_STUDY_PLAN",
    "PROGRESS_SCHEDULE_TUTOR_MEETING": "SCHEDULE_TUTOR_MEETING",
    "STUDY_RIGHT_REVIEW_SUPPORT_OPTIONS": "REVIEW_STUDY_RIGHT",
    "ACADEMIC_DEADLINE_REVIEW_NEXT_STEP": "REVIEW_ACADEMIC_DEADLINE",
}
_PRIORITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_TYPE_ORDER = {name: index for index, name in enumerate(_INTERVENTION_BY_REASON.values())}


class InterventionSuggestionService:
    """Select a small, ordered set of actions from approved recommendations."""

    def suggest(self, value: InterventionInput) -> InterventionAssessment:
        grouped: dict[InterventionType, dict[str, Any]] = {}
        missing: list[str] = []

        for decision in value.recommendation_decisions:
            for reason_code in decision.reason_codes:
                intervention_type = _INTERVENTION_BY_REASON.get(reason_code)
                if intervention_type is None:
                    message = (
                        "No approved intervention mapping for recommendation "
                        f"reason '{reason_code}'."
                    )
                    if message not in missing:
                        missing.append(message)
                    continue

                current = grouped.get(intervention_type)
                if current is None:
                    grouped[intervention_type] = {
                        "priority": decision.priority,
                        "action": decision.action,
                        "reason_codes": [reason_code],
                        "evidence": list(decision.evidence),
                        "source_agents": list(decision.source_agents),
                        "policy_query": decision.policy_query,
                    }
                    continue

                if _priority_value(decision.priority) > _priority_value(
                    current["priority"]
                ):
                    current["priority"] = decision.priority
                _append_unique(current["reason_codes"], reason_code)
                for item in decision.evidence:
                    _append_unique(current["evidence"], item)
                for source in decision.source_agents:
                    _append_unique(current["source_agents"], source)

        suggestions = [
            InterventionSuggestion(
                intervention_type=intervention_type,
                priority=data["priority"],
                action=data["action"],
                reason_codes=tuple(data["reason_codes"]),
                evidence=tuple(data["evidence"]),
                source_agents=tuple(data["source_agents"]),
                policy_query=data["policy_query"],
            )
            for intervention_type, data in grouped.items()
        ]
        suggestions.sort(
            key=lambda item: (
                -_priority_value(item.priority),
                _TYPE_ORDER[item.intervention_type],
            )
        )
        return InterventionAssessment(
            student_id=value.student_id,
            data_status=value.data_status,
            suggestions=tuple(suggestions),
            unavailable_dimensions=tuple(value.unavailable_dimensions),
            missing_information=tuple(missing),
        )


def _priority_value(priority: str) -> int:
    return _PRIORITY_ORDER.get(priority, -1)


def _append_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)
