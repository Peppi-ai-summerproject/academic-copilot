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


_POLICY_QUERIES = {
    "progress": "academic progress deficit tutor support policy",
    "study_right": "expiring study right extension support policy",
    "academic_event": "upcoming academic deadline tutor guidance",
}


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
    ) -> None:
        self._gateway = gateway
        self._policy_gateway = policy_gateway

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
        if risk_complete and risk_data.get("risk_level") == "NONE" and not factors:
            return self._result(
                state,
                recommendations=[],
                missing=[],
                complete=True,
                summary="No confirmed tutor intervention was identified.",
            )

        recommendations: list[dict[str, Any]] = []
        missing: list[str] = []
        policy_used = False

        for factor in factors:
            if not isinstance(factor, dict):
                missing.append("Malformed risk factor could not be mapped.")
                continue
            dimension = factor.get("dimension")
            actions = _actions_for_factor(factor)
            query = _POLICY_QUERIES.get(str(dimension))
            if not actions or query is None:
                missing.append(
                    f"No approved recommendation mapping for risk factor '{dimension}'."
                )
                continue

            try:
                policy_result = await self._policy_gateway.retrieve_policy(query, top_k=3)
            except Exception:
                policy_result = None
            if policy_result is None:
                candidates = []
            else:
                candidates = (
                    _usable_candidates(policy_result.candidates)
                    if policy_result.succeeded
                    else []
                )
            if _has_explicit_conflict(candidates):
                missing.append(f"Conflicting policy evidence for '{dimension}'.")
                continue

            policy_evidence = [_candidate_data(item) for item in candidates]
            if not policy_evidence:
                missing.append(f"Policy evidence unavailable for '{dimension}'.")
            else:
                policy_used = True

            for action, category in actions:
                recommendations.append(
                    {
                        "priority": factor.get("level", "LOW"),
                        "category": category,
                        "action": action,
                        "explanation": _explanation(factor, policy_evidence),
                        "student_evidence": _student_evidence(state, factor),
                        "policy_evidence": policy_evidence,
                        "source_agents": _source_agents(state, dimension),
                        "policy_context_used": bool(policy_evidence),
                    }
                )

        complete = risk_complete and not missing
        summary = _summary(recommendations, complete)
        return self._result(
            state,
            recommendations=recommendations,
            missing=missing,
            complete=complete,
            summary=summary,
            policy_used=policy_used,
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
    ) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            route="recommendation",
            status="SUCCESS" if complete else "PARTIAL",
            summary=summary,
            data={
                "student_id": state.student_id,
                "assessment_status": "COMPLETE" if complete else "PARTIAL",
                "recommendations": recommendations,
                "missing_information": missing,
                "policy_context_used": policy_used,
            },
            evidence=[
                f"{item['category']}: {item['action']}"
                for item in recommendations
            ],
            warnings=list(missing),
        )


def _actions_for_factor(factor: dict[str, Any]) -> list[tuple[str, str]]:
    dimension = factor.get("dimension")
    level = factor.get("level")
    if dimension == "progress":
        actions = [("Review the student's study plan.", "progress")]
        if level in {"MEDIUM", "HIGH"}:
            actions.append(("Schedule a tutor meeting.", "progress"))
        return actions
    if dimension == "study_right":
        return [("Check study-right extension/support options.", "study_right")]
    if dimension == "academic_event":
        return [(
            "Review the upcoming academic deadline with the student and agree "
            "on the required next step.",
            "deadline",
        )]
    return []


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


def _student_evidence(state: AgentState, factor: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = [{
        "source_agent": "risk",
        "reason": factor.get("reason"),
        "values": dict(factor.get("values", {})),
    }]
    supporting_route = {
        "progress": "progress",
        "study_right": "study_rights",
    }.get(factor.get("dimension"))
    result = state.agent_results.get(supporting_route) if supporting_route else None
    if isinstance(result, AgentResult) and result.status != "FAILED":
        evidence.append({
            "source_agent": supporting_route,
            "data": dict(result.data),
        })
    return evidence


def _source_agents(state: AgentState, dimension: Any) -> list[str]:
    agents = ["risk"]
    supporting = {"progress": "progress", "study_right": "study_rights"}.get(dimension)
    supporting_result = state.agent_results.get(supporting) if supporting else None
    if isinstance(supporting_result, AgentResult) and supporting_result.status != "FAILED":
        agents.append(supporting)
    return agents


def _explanation(factor: dict[str, Any], policy_evidence: list[dict[str, Any]]) -> str:
    fact = f"Verified student fact: {factor.get('reason', 'confirmed risk factor')}"
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
