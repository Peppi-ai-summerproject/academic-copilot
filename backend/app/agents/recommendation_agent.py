"""Policy-grounded advisory recommendations for tutor teachers."""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState
from app.agents.types import AgentResult
from app.gateways.academic_tools import AcademicToolGateway
from app.gateways.policy_context import (
    PolicyContextGateway,
    PolicyEvidenceCandidate,
)
from app.services.recommendation_engine import (
    RecommendationEngine,
    RecommendationInput,
    SupportingEvidence,
)


class RecommendationAgent:
    name = "RecommendationAgent"
    description = (
        "Converts authoritative risk factors and retrieved academic-policy "
        "evidence into advisory tutor recommendations."
    )

    def __init__(
        self,
        gateway: AcademicToolGateway,
        policy_gateway: PolicyContextGateway,
        recommendation_engine: RecommendationEngine | None = None,
    ) -> None:
        # The gateway remains in the constructor for the shared registry contract.
        # Recommendation facts come from prior agent results, never fresh tool calls.
        self._gateway = gateway
        self._policy_gateway = policy_gateway
        self._engine = recommendation_engine or RecommendationEngine()

    async def run(self, state: AgentState) -> AgentResult:
        prerequisite_error = self._validate_prerequisites(state)
        risk_result = state.agent_results.get("risk")
        if prerequisite_error or not self._valid_risk_result(risk_result):
            missing = [prerequisite_error or "A valid risk assessment is required."]
            return self._result(
                state,
                recommendations=[],
                missing=missing,
                complete=False,
                summary="Recommendations are unavailable until a valid risk assessment runs first.",
            )

        risk_data = risk_result.data
        factors = risk_data.get("risk_factors", [])
        risk_complete = bool(risk_data.get("assessment_complete"))
        assessment = self._engine.evaluate(
            RecommendationInput(
                student_id=state.student_id,
                risk_level=risk_data.get("risk_level"),
                risk_factors=tuple(factors),
                assessment_status="COMPLETE" if risk_complete else "PARTIAL",
                unavailable_dimensions=tuple(
                    risk_data.get("unavailable_dimensions", [])
                ),
                supporting_evidence=_supporting_evidence(state),
            )
        )
        if assessment.complete and risk_data.get("risk_level") == "NONE" and not factors:
            return self._result(
                state,
                recommendations=[],
                missing=[],
                complete=True,
                summary="No confirmed tutor intervention was identified.",
                unavailable_dimensions=[],
            )

        recommendations: list[dict[str, Any]] = []
        missing: list[str] = list(assessment.missing_information)
        policy_used = False
        policy_cache: dict[str, list[PolicyEvidenceCandidate] | None] = {}

        for decision in assessment.decisions:
            query = decision.policy_query
            if query not in policy_cache:
                try:
                    policy_result = await self._policy_gateway.retrieve_policy(
                        query, top_k=3
                    )
                except Exception:
                    policy_result = None
                policy_cache[query] = (
                    _usable_candidates(policy_result.candidates)
                    if policy_result is not None and policy_result.succeeded
                    else []
                )
            candidates = policy_cache[query] or []
            if _has_explicit_conflict(candidates):
                message = (
                    "Conflicting policy evidence for "
                    f"'{decision.recommendation_type}'."
                )
                if message not in missing:
                    missing.append(message)
                continue

            policy_evidence = [_candidate_data(item) for item in candidates]
            if not policy_evidence:
                message = (
                    "Policy evidence unavailable for "
                    f"'{decision.recommendation_type}'."
                )
                if message not in missing:
                    missing.append(message)
            else:
                policy_used = True

            recommendation = decision.to_dict()
            recommendation.update({
                "explanation": _explanation(recommendation, policy_evidence),
                "policy_evidence": policy_evidence,
                "policy_context_used": bool(policy_evidence),
            })
            recommendations.append(recommendation)

        complete = assessment.complete and not missing
        summary = _summary(recommendations, complete)
        return self._result(
            state,
            recommendations=recommendations,
            missing=missing,
            complete=complete,
            summary=summary,
            policy_used=policy_used,
            unavailable_dimensions=list(assessment.unavailable_dimensions),
        )

    @staticmethod
    def _validate_prerequisites(state: AgentState) -> str | None:
        if "risk" not in state.completed_agents:
            return "RiskDetectionAgent must complete before RecommendationAgent."
        selected = state.selected_agents
        if "recommendation" in selected and "risk" in selected:
            risk_index = selected.index("risk")
            recommendation_index = selected.index("recommendation")
            if risk_index > recommendation_index:
                return "Selected agent order must place risk before recommendation."
            for route in ("progress", "study_rights"):
                if route in selected and selected.index(route) > risk_index:
                    return (
                        "Selected prerequisite order must be progress, study_rights, "
                        "risk, then recommendation."
                    )
            if (
                "progress" in selected
                and "study_rights" in selected
                and selected.index("progress") > selected.index("study_rights")
            ):
                return (
                    "Selected prerequisite order must be progress, study_rights, "
                    "risk, then recommendation."
                )
        return None

    @staticmethod
    def _valid_risk_result(result: Any) -> bool:
        return (
            isinstance(result, AgentResult)
            and result.route == "risk"
            and result.status != "FAILED"
            and isinstance(result.data, dict)
            and isinstance(result.data.get("risk_factors"), list)
        )

    def _result(
        self,
        state: AgentState,
        *,
        recommendations: list[dict[str, Any]],
        missing: list[str],
        complete: bool,
        summary: str,
        policy_used: bool = False,
        unavailable_dimensions: list[str] | None = None,
    ) -> AgentResult:
        assessment_status = "COMPLETE" if complete else "PARTIAL"
        return AgentResult(
            agent_name=self.name,
            route="recommendation",
            status="SUCCESS" if complete else "PARTIAL",
            summary=summary,
            data={
                "student_id": state.student_id,
                "assessment_status": assessment_status,
                "data_status": assessment_status,
                "recommendations": recommendations,
                "missing_information": missing,
                "unavailable_dimensions": unavailable_dimensions or [],
                "policy_context_used": policy_used,
            },
            evidence=[
                f"{item['category']}: {item['action']}"
                for item in recommendations
            ],
            warnings=list(missing),
        )


def _usable_candidates(candidates: tuple[PolicyEvidenceCandidate, ...]) -> list[PolicyEvidenceCandidate]:
    return [item for item in candidates if item.chunk_id and (item.source or item.metadata)]


def _has_explicit_conflict(candidates: list[PolicyEvidenceCandidate]) -> bool:
    return any(
        item.metadata.get("contradictory") is True
        or item.metadata.get("conflict") is True
        or str(item.metadata.get("policy_status", "")).upper() in {"CONFLICT", "AMBIGUOUS"}
        for item in candidates
    )


def _candidate_data(candidate: PolicyEvidenceCandidate) -> dict[str, Any]:
    return {
        "chunk_id": candidate.chunk_id,
        "score": candidate.score,
        "source": candidate.source,
        "metadata": dict(candidate.metadata),
        "excerpt": candidate.text,
    }


def _supporting_evidence(state: AgentState) -> dict[str, SupportingEvidence]:
    evidence: dict[str, SupportingEvidence] = {}
    for dimension, route in (("progress", "progress"), ("study_right", "study_rights")):
        result = state.agent_results.get(route)
        if isinstance(result, AgentResult) and result.status != "FAILED":
            evidence[dimension] = SupportingEvidence(route, dict(result.data))
    return evidence


def _explanation(
    recommendation: dict[str, Any], policy_evidence: list[dict[str, Any]]
) -> str:
    student_evidence = recommendation.get("student_evidence", [])
    reason = (
        student_evidence[0].get("reason", "confirmed risk factor")
        if student_evidence
        else "confirmed risk factor"
    )
    fact = f"Verified student fact: {reason}"
    if policy_evidence:
        return f"{fact} Retrieved policy guidance supports this advisory tutor action."
    return (
        f"{fact} Supporting policy context was unavailable; this is a qualified "
        "fact-based advisory action, not a statement of university policy."
    )


def _summary(recommendations: list[dict[str, Any]], complete: bool) -> str:
    if not recommendations:
        return "No supported tutor recommendation could be produced."
    qualifier = "Policy-grounded" if complete else "Partial"
    return f"{qualifier} advisory recommendations: {len(recommendations)} action(s)."
