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
        summary = self._build_summary(
            student_name, risk_level, factors, complete, unavailable
        )
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
                "tutor_facing_presentation": True,
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
        unavailable: list[str],
    ) -> str:
        assessment = "COMPLETE" if complete else ("PARTIAL" if factors else "UNAVAILABLE")
        displayed_level = risk_level if complete or factors else "UNAVAILABLE"
        lines = [
            "Academic risk",
            student_name,
            "",
            f"Risk level: {displayed_level}",
            f"Assessment: {assessment}",
        ]
        if factors:
            lines.extend(["", "Why this student needs attention"])
            lines.extend(f"• {factor['reason'].rstrip('.')}" for factor in factors)
        elif complete:
            lines.extend(
                [
                    "",
                    "Verified evidence",
                    "• No confirmed academic risk factors were found in the assessed dimensions.",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "Required information",
                    "• Sufficient academic evidence was unavailable for a reliable risk level.",
                ]
            )
        if unavailable:
            lines.extend(["", "Data availability"])
            lines.append("Some supporting information was unavailable:")
            lines.extend(f"• {_dimension_label(item)}" for item in unavailable)
            lines.append("Missing information is not interpreted as no risk.")
        return "\n".join(lines)

    def _failed_system_result(self) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            route="risk",
            status="FAILED",
            summary="Risk assessment could not be completed due to a system error.",
            errors=["RISK_ASSESSMENT_UNAVAILABLE"],
        )


def _dimension_label(value: str) -> str:
    return {
        "progress": "Academic progress information",
        "study_right": "Study-right information",
        "academic_events": "Academic event information",
    }.get(value, "Supporting academic information")
