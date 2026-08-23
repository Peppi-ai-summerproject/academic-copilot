"""Progress Analysis Agent — Issue #81.

Analyzes student academic progress based on completed credits
and curriculum requirements. Detects delayed students and
generates progress summaries for tutor teachers.

Implements the AcademicAgent Protocol defined in base.py.
"""

from __future__ import annotations
from app.agents.base import AcademicAgent
from app.agents.types import AgentResult
from app.agents.state import AgentState as FullAgentState  # noqa
from app.gateways.academic_tools import AcademicToolGateway, MCPAcademicToolGateway
from app.services.progress_explanation_service import (
    ProgressExplanationInput,
    ProgressExplanationService,
)


class ProgressAnalysisAgent:
    """Analyzes student academic ECTS progress against curriculum requirements.

    Responsibilities:
    - Calculates total completed ECTS credits
    - Compares actual progress to expected curriculum milestones
    - Detects students who are behind, on track, or ahead
    - Generates a plain-language progress summary for the tutor teacher
    - Provides structured data for downstream agents (Recommendation, Risk)

    Does NOT call any LLM. Does NOT generate the final Telegram response.

    Attributes:
        name: Agent identifier used in routing and state tracking.
        description: Human-readable description for registry and logging.
    """

    name: str = "ProgressAnalysisAgent"
    description: str = (
        "Analyzes student academic ECTS progress against curriculum "
        "requirements. Detects delayed students and generates progress summaries."
    )

    def __init__(
        self,
        gateway: AcademicToolGateway | None = None,
        explanation_service: ProgressExplanationService | None = None,
    ) -> None:
        """Create the agent with an injectable academic tool boundary."""
        self._gateway = gateway or MCPAcademicToolGateway()
        self._explanation_service = explanation_service or ProgressExplanationService()

    async def run(self, state: FullAgentState) -> AgentResult:
        """Analyze academic progress for the student in the current state.

        Retrieves progress data via MCP-compatible service layer.
        Returns an AgentResult with structured progress data and
        a plain-language summary suitable for downstream agents.

        Args:
            state: The shared agent state containing student_id.

        Returns:
            AgentResult with route="progress" and progress data.
        """
        student_id = state.student_id

        if student_id is None:
            return AgentResult(
                agent_name=self.name,
                route="progress",
                status="FAILED",
                summary="No student ID available in agent state.",
                errors=["student_id is None — cannot analyse progress."],
            )

        try:
            # Verify student exists
            student_result = await self._gateway.get_student(student_id)
            if not student_result.get("success"):
                return AgentResult(
                    agent_name=self.name,
                    route="progress",
                    status="FAILED",
                    summary=f"Student with ID {student_id} was not found.",
                    errors=[student_result.get("error", "STUDENT_NOT_FOUND")],
                )

            student = student_result["student"]
            student_name = student.get("name", f"Student {student_id}")
            programme = student.get("programme", "Unknown")

            # Get academic progress
            progress_result = await self._gateway.get_progress(student_id)
            explanation = self._explanation_service.explain(
                ProgressExplanationInput(
                    student_id=student_id,
                    progress_result=progress_result,
                )
            )
            if not progress_result.get("success"):
                return AgentResult(
                    agent_name=self.name,
                    route="progress",
                    status="PARTIAL",
                    summary=_unavailable_progress_summary(student_name, programme),
                    data={
                        "progress_explanation": explanation.to_dict(),
                        "tutor_facing_presentation": True,
                    },
                    warnings=[progress_result.get("error", "PROGRESS_UNAVAILABLE")],
                )

            progress = progress_result["progress"]
            completed = progress.get("completed_ects", 0) or 0
            expected = progress.get("expected_ects", 0) or 0
            difference = progress.get("difference_ects", 0) or 0
            status = progress.get("status", "UNKNOWN")
            semester = progress.get("current_semester", "?")
            percentage = progress.get("progress_percentage", 0.0) or 0.0

            # Generate plain-language summary
            summary = _build_summary(
                student_name=student_name,
                programme=programme,
                completed=completed,
                expected=expected,
                difference=difference,
                status=status,
                semester=semester,
                percentage=percentage,
            )

            agent_status = _map_progress_status(status)

            return AgentResult(
                agent_name=self.name,
                route="progress",
                status=agent_status,
                summary=summary,
                data={
                    "student_id": student_id,
                    "student_name": student_name,
                    "programme": programme,
                    "current_semester": semester,
                    "completed_ects": completed,
                    "expected_ects": expected,
                    "difference_ects": difference,
                    "progress_percentage": round(percentage, 2),
                    "progress_status": status,
                    "is_behind": status == "BEHIND",
                    "is_ahead": status == "AHEAD",
                    "is_on_track": status == "ON_TRACK",
                    "progress_explanation": explanation.to_dict(),
                    "tutor_facing_presentation": True,
                },
                evidence=[
                    f"Completed ECTS: {completed}",
                    f"Expected ECTS by semester {semester}: {expected}",
                    f"Progress status: {status}",
                ],
            )

        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                route="progress",
                status="FAILED",
                summary="Progress analysis could not be completed due to a system error.",
                errors=[f"Unexpected error: {exc}"],
            )


def _build_summary(
    student_name: str,
    programme: str,
    completed: int,
    expected: int,
    difference: int,
    status: str,
    semester: int | str,
    percentage: float,
) -> str:
    """Present existing progress values without calculating new classifications."""
    difference_label = {
        "BEHIND": f"{abs(difference)} ECTS behind",
        "AHEAD": f"{abs(difference)} ECTS ahead",
    }.get(status, f"{difference} ECTS")
    lines = [
        "Academic progress",
        f"{student_name} · {programme}",
        "",
        f"Status: {status}",
    ]
    if _map_progress_status(status) == "PARTIAL":
        lines.append("Assessment: PARTIAL")
    lines.extend(
        [
            "",
            "Key facts",
            f"• Completed: {completed} ECTS",
            f"• Expected: {expected} ECTS by semester {semester}",
            f"• Difference: {difference_label}",
            f"• Progress: {percentage:.1f}% of expected",
        ]
    )
    return "\n".join(lines)


def _unavailable_progress_summary(student_name: str, programme: str) -> str:
    return "\n".join(
        [
            "Academic progress",
            f"{student_name} · {programme}",
            "",
            "Assessment: PARTIAL",
            "",
            "Availability",
            "• Progress data could not be verified.",
            "• Missing information is not confirmation that there is no risk.",
        ]
    )


def _map_progress_status(progress_status: str) -> str:
    """Map progress service status to AgentStatus."""
    if progress_status == "BEHIND":
        return "PARTIAL"
    return "SUCCESS"
