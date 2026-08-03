"""Deterministic academic risk detection agent for Issue #85."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from app.agents.state import AgentState
from app.agents.types import AgentResult
from app.gateways.academic_tools import AcademicToolGateway, MCPAcademicToolGateway
from app.services.risk_policy import (
    event_risk_factors,
    highest_risk_level,
    progress_risk_factors,
    study_right_risk_factors,
)


class RiskDetectionAgent:
    name = "RiskDetectionAgent"
    description = (
        "Detects deterministic academic risks from progress, study rights, "
        "and globally applicable academic deadlines."
    )

    def __init__(
        self,
        gateway: AcademicToolGateway | None = None,
        *,
        date_provider: Callable[[], date] = date.today,
    ) -> None:
        self._gateway = gateway or MCPAcademicToolGateway()
        self._date_provider = date_provider

    async def run(self, state: AgentState) -> AgentResult:
        student_id = state.student_id
        if student_id is None:
            return AgentResult(
                agent_name=self.name,
                route="risk",
                status="FAILED",
                summary="No student ID available in agent state.",
                errors=["STUDENT_ID_MISSING"],
            )

        try:
            student_result = await self._gateway.get_student(student_id)
        except Exception:
            return self._failed_system_result()
        if not isinstance(student_result, dict):
            return self._failed_system_result()
        if not student_result.get("success"):
            return AgentResult(
                agent_name=self.name,
                route="risk",
                status="FAILED",
                summary=f"Student with ID {student_id} was not found.",
                errors=[student_result.get("error", "STUDENT_NOT_FOUND")],
            )

        student = student_result.get("student", {})
        student_name = student.get("name", f"Student {student_id}")
        factors: list[dict[str, Any]] = []
        unavailable: list[str] = []
        warnings: list[str] = []

        progress = await self._safe_call(self._gateway.get_progress, student_id)
        if (
            not isinstance(progress, dict)
            or not progress.get("success")
            or not self._valid_progress(progress.get("progress"))
        ):
            self._mark_unavailable("progress", unavailable, warnings)
        else:
            factors.extend(progress_risk_factors(progress["progress"]))

        study_right = await self._safe_call(self._gateway.get_study_right, student_id)
        if (
            not isinstance(study_right, dict)
            or not study_right.get("success")
            or not self._valid_study_right(study_right.get("study_right"))
        ):
            self._mark_unavailable("study_right", unavailable, warnings)
        else:
            factors.extend(study_right_risk_factors(study_right["study_right"]))

        events = await self._safe_call(self._gateway.get_upcoming_events)
        if (
            not isinstance(events, dict)
            or not events.get("success")
            or not isinstance(events.get("events"), list)
        ):
            self._mark_unavailable("academic_events", unavailable, warnings)
        else:
            event_factors, malformed = event_risk_factors(
                events["events"], today=self._date_provider()
            )
            factors.extend(event_factors)
            if malformed:
                self._mark_unavailable("academic_events", unavailable, warnings)

        complete = not unavailable
        risk_level = highest_risk_level(factors)
        summary = self._build_summary(student_name, risk_level, factors, complete)
        evidence = [
            f"{factor['evidence_source']}: {factor['reason']} Values: {factor['values']}"
            for factor in factors
        ]
        if complete and not factors:
            evidence.append("All required risk dimensions were assessed.")

        return AgentResult(
            agent_name=self.name,
            route="risk",
            status="SUCCESS" if complete else "PARTIAL",
            summary=summary,
            data={
                "student_id": student_id,
                "student_name": student_name,
                "risk_level": risk_level,
                "risk_factors": factors,
                "assessment_complete": complete,
                "unavailable_dimensions": unavailable,
            },
            evidence=evidence,
            warnings=warnings,
        )

    @staticmethod
    async def _safe_call(operation: Callable[..., Any], *args: Any) -> Any:
        try:
            return await operation(*args)
        except Exception:
            return None

    @staticmethod
    def _mark_unavailable(
        dimension: str, unavailable: list[str], warnings: list[str]
    ) -> None:
        if dimension not in unavailable:
            unavailable.append(dimension)
            warnings.append(f"{dimension} data is unavailable.")

    @staticmethod
    def _valid_progress(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and isinstance(value.get("status"), str)
            and isinstance(value.get("completed_ects"), (int, float))
            and isinstance(value.get("expected_ects"), (int, float))
        )

    @staticmethod
    def _valid_study_right(value: Any) -> bool:
        return isinstance(value, dict) and isinstance(value.get("status"), str)

    @staticmethod
    def _build_summary(
        student_name: str,
        risk_level: str,
        factors: list[dict[str, Any]],
        complete: bool,
    ) -> str:
        if factors:
            reasons = " ".join(factor["reason"] for factor in factors)
            qualifier = "Partial assessment: " if not complete else ""
            return f"{qualifier}{student_name} has {risk_level} academic risk. {reasons}"
        if complete:
            return f"{student_name} has no confirmed academic risk factors."
        return (
            f"Risk assessment for {student_name} is inconclusive because required "
            "academic data is unavailable."
        )

    def _failed_system_result(self) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            route="risk",
            status="FAILED",
            summary="Risk assessment could not be completed due to a system error.",
            errors=["RISK_ASSESSMENT_UNAVAILABLE"],
        )
