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

    def __init__(self, gateway: AcademicToolGateway | None = None) -> None:
        """Create the agent with an injectable academic tool boundary."""
        self._gateway = gateway or MCPAcademicToolGateway()

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
            if not progress_result.get("success"):
                return AgentResult(
                    agent_name=self.name,
                    route="progress",
                    status="PARTIAL",
                    summary=(
                        f"{student_name} is enrolled in {programme}. "
                        "Progress data could not be retrieved — "
                        "curriculum data may be missing."
                    ),
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
    """Build a plain-language progress summary for tutor teachers."""
    if status == "BEHIND":
        behind = abs(difference)
        return (
            f"{student_name} ({programme}) is behind on academic progress. "
            f"They have completed {completed} ECTS but {expected} ECTS were "
            f"expected by semester {semester}. "
            f"They are {behind} ECTS behind schedule "
            f"({percentage:.1f}% of expected progress)."
        )
    elif status == "AHEAD":
        ahead = abs(difference)
        return (
            f"{student_name} ({programme}) is ahead of schedule. "
            f"They have completed {completed} ECTS, which is {ahead} ECTS "
            f"more than the {expected} ECTS expected by semester {semester} "
            f"({percentage:.1f}% of expected progress)."
        )
    else:
        return (
            f"{student_name} ({programme}) is on track with their studies. "
            f"They have completed {completed} ECTS, meeting the expected "
            f"{expected} ECTS milestone for semester {semester} "
            f"({percentage:.1f}% of expected progress)."
        )


def _map_progress_status(progress_status: str) -> str:
    """Map progress service status to AgentStatus."""
    if progress_status == "BEHIND":
        return "PARTIAL"
    return "SUCCESS"
