"""User-facing responses for non-academic and safely blocked chat requests."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.intent_detection import IntentResult
from app.agents.types import AgentRoute


STUDENT_CONTEXT_ROUTES = frozenset(
    {"progress", "study_rights", "risk", "recommendation", "reporting"}
)


@dataclass(frozen=True)
class FallbackResponseService:
    """Generate deterministic fallbacks without academic data or agent execution."""

    def for_non_academic(self, intent_result: IntentResult) -> str:
        if intent_result.intent == "general":
            return (
                "Hi! I'm Academic Copilot. I can help with student progress, "
                "study rights, academic risk, upcoming academic events and "
                "deadlines, recommendations, and academic summaries or reports."
            )
        if intent_result.is_ambiguous or intent_result.reason == "ambiguous":
            return (
                "Please clarify what you want to check for this student, such as "
                "progress, academic risk, study rights, or upcoming events."
            )
        return (
            "I can't help with that request. Academic Copilot is focused on "
            "student progress, study rights, academic risks, events, "
            "recommendations, and tutor reports."
        )

    @staticmethod
    def for_missing_student_context() -> str:
        return (
            "Please provide the student identifier so I can perform this "
            "academic analysis for the correct student."
        )

    @staticmethod
    def for_internal_routing_failure() -> str:
        return (
            "I couldn't prepare the academic analysis safely. Please try again "
            "or clarify the academic information you need."
        )

    @staticmethod
    def requires_student_context(routes: tuple[AgentRoute, ...]) -> bool:
        return any(route in STUDENT_CONTEXT_ROUTES for route in routes)
