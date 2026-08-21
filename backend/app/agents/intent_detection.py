"""Deterministic natural-language intent detection for academic requests.

This module classifies only.  It deliberately does not select or execute agents;
callers can use ``IntentResult.route`` in a later routing layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal, cast

from app.agents.routing import ROUTE_INTENT_MAP
from app.agents.types import AgentRoute
from app.agents.tutor_query_intent import detect_tutor_query


IntentName = Literal[
    "calendar",
    "progress",
    "study_rights",
    "risk",
    "recommendation",
    "reporting",
    "communication",
    "academic_data",
    "general",
    "unknown",
]
IntentReason = Literal["matched", "general", "ambiguous", "unsupported"]

_ACADEMIC_ROUTES = frozenset(
    route for route in ROUTE_INTENT_MAP.values() if route != "finish"
)
_AMBIGUOUS_ACADEMIC = re.compile(
    r"\b(student|academic|studies|study|course|degree|tutor)\b"
)

# Patterns are intentionally narrow.  A false negative becomes ``unknown`` and
# can be clarified; a false positive could dispatch the wrong academic agent.
_PATTERNS: dict[AgentRoute, tuple[re.Pattern[str], ...]] = {
    "calendar": (
        re.compile(r"\b(upcoming|next|future)\s+(?:academic\s+)?(?:deadlines?|events?)\b"),
        re.compile(r"\bdeadlines?\b.*\b(?:coming up|upcoming|soon)\b"),
        re.compile(r"\b(?:academic|course|study|semester)\s+(?:deadlines?|calendar|schedule)\b"),
        re.compile(r"\bwhen\s+(?:is|are)\b.*\b(?:deadline|event|exam)\b"),
    ),
    "progress": (
        re.compile(r"\b(?:how is|how are)\s+(?:she|he|they)\s+progress(?:ing)?\b"),
        re.compile(r"\bstudent\b.*\bprogress(?:ing)?\b"),
        re.compile(r"\bprogress(?:ing)?\b.*\bstudent\b"),
        re.compile(r"\b(?:student|studies|academic)\b.*\b(?:on track|falling behind)\b"),
        re.compile(r"\b(?:earned|completed|missing)\s+(?:credits?|ects|courses?)\b"),
    ),
    "study_rights": (
        re.compile(r"\b(?:her|his|their)\s+study[- ]rights?\b"),
        re.compile(r"\bstudy\s+rights?\b"),
        re.compile(r"\b(?:valid|active|expired?|expiring|extend)\b.*\b(?:study|enrolment)\b"),
        re.compile(r"\b(?:study|enrolment)\b.*\b(?:valid|active|expired?|expiring|extension)\b"),
    ),
    "risk": (
        re.compile(r"\b(?:is|are)\s+(?:she|he|they)\s+at risk\b"),
        re.compile(r"\b(?:student|studies|academic)\b.*\bat risk\b"),
        re.compile(r"\bat risk\b.*\b(?:student|studies|academic)\b"),
        re.compile(r"\bacademic risk\b"),
        re.compile(r"\bwarning signs?\b"),
    ),
    "recommendation": (
        re.compile(r"\b(?:recommend(?:ation)?|advice|next steps?)\b.*\b(?:student|studies|academic)\b"),
        re.compile(r"\b(?:student|studies|academic)\b.*\b(?:recommend(?:ation)?|advice|next steps?)\b"),
        re.compile(r"\bwhat should (?:i|we) do\b.*\b(?:student|studies|academic)\b"),
        re.compile(r"\bhow (?:can|should) (?:i|we) (?:help|support)\b.*\bstudent\b"),
    ),
    "reporting": (
        re.compile(r"\b(?:academic|student|study|progress)\s+(?:summary|report|overview)\b"),
        re.compile(r"\b(?:summary|report|overview)\b.*\b(?:student|academic|studies)\b"),
    ),
    "communication": (
        re.compile(r"\b(?:draft|compose|write|prepare)\b.*\b(?:email|message|letter)\b"),
        re.compile(r"\b(?:email|message|letter)\b.*\b(?:student|tutor)\b"),
        re.compile(r"\bcontact\b.*\b(?:student|tutor)\b"),
    ),
    "finish": (),
}

_GENERAL = (
    re.compile(r"^(?:hi|hello|hey|good (?:morning|afternoon|evening))[!. ]*$"),
    re.compile(r"^(?:thanks?|thank you)[!. ]*$"),
    re.compile(r"\bwhat can you (?:do|help me with)\b"),
    re.compile(r"\bhow can you help(?: me)?\b"),
    re.compile(r"\bwhat are your (?:capabilities|features)\b"),
)


@dataclass(frozen=True)
class IntentResult:
    """Typed classification result with evidence and safe fallback metadata."""

    intent: IntentName
    route: AgentRoute | None
    confidence: float
    matched_terms: tuple[str, ...]
    is_ambiguous: bool
    reason: IntentReason
    capability: str | None = None
    entity_references: tuple[tuple[str, str], ...] = ()
    parameters: dict[str, str] | None = None


class IntentDetector:
    """Classify one user utterance without external services or side effects."""

    def detect(self, message: str) -> IntentResult:
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        normalized = " ".join(message.casefold().split())
        if not normalized:
            raise ValueError("message must not be empty")

        matches: dict[AgentRoute, list[str]] = {}
        for route, patterns in _PATTERNS.items():
            found = [match.group(0) for pattern in patterns if (match := pattern.search(normalized))]
            if found:
                matches[route] = found

        # Preserve existing explicit routing aliases, while requiring context for
        # generic one-word aliases embedded in unrelated sentences.
        explicit_route = ROUTE_INTENT_MAP.get(normalized)
        if explicit_route in _ACADEMIC_ROUTES:
            matches.setdefault(explicit_route, []).append(normalized)

        if matches:
            best_count = max(len(terms) for terms in matches.values())
            winners = [route for route, terms in matches.items() if len(terms) == best_count]
            if len(winners) == 1:
                route = winners[0]
                terms = tuple(dict.fromkeys(matches[route]))
                return IntentResult(
                    intent=cast(IntentName, route),
                    route=route,
                    confidence=min(0.99, 0.8 + 0.05 * (len(terms) - 1)),
                    matched_terms=terms,
                    is_ambiguous=False,
                    reason="matched",
                )
            evidence = tuple(
                dict.fromkeys(term for route in winners for term in matches[route])
            )
            return IntentResult("unknown", None, 0.0, evidence, True, "ambiguous")

        if tutor_query := detect_tutor_query(message):
            return IntentResult(
                "academic_data",
                "academic_data",
                0.9,
                (tutor_query.capability,),
                False,
                "matched",
                tutor_query.capability,
                tutor_query.entity_references,
                tutor_query.parameters,
            )

        if any(pattern.search(normalized) for pattern in _GENERAL):
            return IntentResult("general", None, 0.95, (), False, "general")

        academic_but_vague = bool(_AMBIGUOUS_ACADEMIC.search(normalized))
        return IntentResult(
            "unknown",
            None,
            0.0,
            (),
            academic_but_vague,
            "ambiguous" if academic_but_vague else "unsupported",
        )


def detect_intent(message: str) -> IntentResult:
    """Convenience entry point for the stateless default detector."""
    return IntentDetector().detect(message)
