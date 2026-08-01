"""Study Rights Agent — Issue #82.

Retrieves and analyses study right status for a student.
Detects expiring, extended, or expired study rights and
generates actionable summaries for tutor teachers.

Implements the AcademicAgent Protocol defined in base.py.
"""

from __future__ import annotations

from app.agents.base import AgentResult, AcademicAgent
from app.agents.state import AgentState as FullAgentState
from app.db.database import SessionLocal
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.student_repository import StudentRepository
from app.services.study_right_service import StudyRightService
from app.services.student_service import StudentService


# Status values that indicate a student needs attention
_AT_RISK_STATUSES = frozenset({"EXPIRES_SOON", "EXTENDED", "EXPIRED"})


class StudyRightsAgent:
    """Retrieves and analyses student study right status.

    Responsibilities:
    - Retrieves study right record for the student
    - Detects study rights that are expiring, extended, or expired
    - Calculates urgency based on status and extension count
    - Generates actionable summaries for tutor teachers
    - Provides structured data for downstream agents (Risk, Recommendation)

    Does NOT call any LLM. Does NOT generate the final Telegram response.

    Attributes:
        name: Agent identifier used in routing and state tracking.
        description: Human-readable description for registry and logging.
    """

    name: str = "StudyRightsAgent"
    description: str = (
        "Retrieves and analyses student study right status. "
        "Detects expiring, extended, or expired study rights and "
        "generates actionable summaries for tutor teachers."
    )

    async def run(self, state: FullAgentState) -> AgentResult:
        """Analyse study right status for the student in the current state.

        Retrieves study right data via service layer.
        Returns an AgentResult with structured study right data and
        a plain-language summary for downstream agents.

        Args:
            state: The shared agent state containing student_id.

        Returns:
            AgentResult with route="study_rights" and study right data.
        """
        student_id = state.student_id

        if student_id is None:
            return AgentResult(
                agent_name=self.name,
                route="study_rights",
                status="FAILED",
                summary="No student ID available in agent state.",
                errors=["student_id is None — cannot retrieve study right."],
            )

        db = SessionLocal()
        try:
            student_service = StudentService(StudentRepository(db))
            study_right_service = StudyRightService(StudyRightRepository(db))

            # Verify student exists
            student_result = student_service.get_student(student_id)
            if not student_result.get("success"):
                return AgentResult(
                    agent_name=self.name,
                    route="study_rights",
                    status="FAILED",
                    summary=f"Student with ID {student_id} was not found.",
                    errors=[student_result.get("error", "STUDENT_NOT_FOUND")],
                )

            student = student_result["student"]
            student_name = student.get("name", f"Student {student_id}")
            programme = student.get("programme", "Unknown")

            # Get study right
            study_right_result = study_right_service.get_study_right(student_id)
            if not study_right_result.get("success"):
                return AgentResult(
                    agent_name=self.name,
                    route="study_rights",
                    status="PARTIAL",
                    summary=(
                        f"{student_name} is enrolled in {programme}. "
                        "Study right record could not be retrieved."
                    ),
                    warnings=[
                        study_right_result.get("error", "STUDY_RIGHT_NOT_FOUND")
                    ],
                )

            study_right = study_right_result["study_right"]
            sr_status = study_right.get("status", "UNKNOWN")
            extension_count = study_right.get("extension_count", 0) or 0
            is_expiring_soon = study_right.get("is_expiring_soon", False)
            expiration_date = study_right.get("expiration_date") or study_right.get("end_date")

            # Serialize date if needed
            if hasattr(expiration_date, "isoformat"):
                expiration_date_str = expiration_date.isoformat()
            else:
                expiration_date_str = str(expiration_date) if expiration_date else None

            # Determine urgency
            needs_attention = sr_status in _AT_RISK_STATUSES
            urgency = _calculate_urgency(sr_status, extension_count)

            # Build summary
            summary = _build_summary(
                student_name=student_name,
                programme=programme,
                sr_status=sr_status,
                extension_count=extension_count,
                expiration_date_str=expiration_date_str,
                needs_attention=needs_attention,
            )

            agent_status = "PARTIAL" if needs_attention else "SUCCESS"

            return AgentResult(
                agent_name=self.name,
                route="study_rights",
                status=agent_status,
                summary=summary,
                data={
                    "student_id": student_id,
                    "student_name": student_name,
                    "programme": programme,
                    "study_right_status": sr_status,
                    "extension_count": extension_count,
                    "is_expiring_soon": is_expiring_soon,
                    "expiration_date": expiration_date_str,
                    "needs_attention": needs_attention,
                    "urgency": urgency,
                    "max_extensions_reached": extension_count >= 2,
                },
                evidence=[
                    f"Study right status: {sr_status}",
                    f"Extension count: {extension_count}",
                    f"Expiration date: {expiration_date_str}",
                ],
                warnings=(
                    [f"Study right status is {sr_status} — requires tutor attention."]
                    if needs_attention else []
                ),
            )

        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                route="study_rights",
                status="FAILED",
                summary="Study right analysis could not be completed due to a system error.",
                errors=[f"Unexpected error: {exc}"],
            )
        finally:
            db.close()


def _calculate_urgency(sr_status: str, extension_count: int) -> str:
    """Calculate urgency level based on study right status and extensions."""
    if sr_status == "EXPIRED":
        return "CRITICAL"
    if sr_status == "EXPIRES_SOON" and extension_count >= 2:
        return "CRITICAL"
    if sr_status == "EXPIRES_SOON":
        return "HIGH"
    if sr_status == "EXTENDED" and extension_count >= 2:
        return "HIGH"
    if sr_status == "EXTENDED":
        return "MEDIUM"
    return "LOW"


def _build_summary(
    student_name: str,
    programme: str,
    sr_status: str,
    extension_count: int,
    expiration_date_str: str | None,
    needs_attention: bool,
) -> str:
    """Build a plain-language study right summary for tutor teachers."""
    exp_str = f" (expires {expiration_date_str})" if expiration_date_str else ""

    if sr_status == "EXPIRED":
        return (
            f"{student_name} ({programme}) has an EXPIRED study right{exp_str}. "
            "They cannot currently attend courses or receive credits. "
            "Immediate administrative action is required."
        )
    elif sr_status == "EXPIRES_SOON":
        ext_note = (
            " They have already used all available extensions."
            if extension_count >= 2
            else f" They have used {extension_count} extension(s) so far."
        )
        return (
            f"{student_name} ({programme}) has a study right expiring soon{exp_str}.{ext_note} "
            "The student should be contacted urgently to discuss their study plan."
        )
    elif sr_status == "EXTENDED":
        return (
            f"{student_name} ({programme}) is on an extended study right "
            f"(extension {extension_count} of 2){exp_str}. "
            "Monitor progress closely and ensure the student is on track to graduate."
        )
    elif sr_status == "GRADUATED":
        return (
            f"{student_name} ({programme}) has graduated. "
            "Study right is no longer active."
        )
    else:
        return (
            f"{student_name} ({programme}) has an active study right{exp_str}. "
            "No immediate action required."
        )
