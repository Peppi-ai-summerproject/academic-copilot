"""Deterministic tutor-facing presentation of grounded recommendations.

The renderer composes values chosen by recommendation, intervention, and
explanation services.  It never calculates academic facts or selects actions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ScenarioTemplate:
    """Presentation labels for one upstream recommendation type."""

    title: str
    situation_label: str


@dataclass(frozen=True)
class RecommendationTemplateInput:
    """Already-grounded values accepted by the presentation layer."""

    student_id: int | None
    data_status: str
    recommendations: tuple[Mapping[str, Any], ...]
    student_name: str | None = None
    interventions: tuple[Mapping[str, Any], ...] = ()
    missing_information: tuple[str, ...] = ()
    unavailable_dimensions: tuple[str, ...] = ()
    risk_explanation: Mapping[str, Any] | None = None
    progress_explanation: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RenderedRecommendation:
    """Channel-independent rendered recommendation presentation."""

    text: str
    sections: tuple[str, ...]
    scenarios: tuple[str, ...]
    data_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_DEFAULT_SCENARIOS = {
    "monitoring": ScenarioTemplate("Normal academic monitoring", "Current situation"),
    "progress": ScenarioTemplate("Academic progress support", "Progress concern"),
    "study_right": ScenarioTemplate("Study-right support", "Study-right concern"),
    "deadline": ScenarioTemplate("Academic deadline support", "Deadline concern"),
}


class RecommendationTemplateService:
    """Compose reusable sections without changing upstream meaning or order."""

    def __init__(
        self,
        scenarios: Mapping[str, ScenarioTemplate] | None = None,
    ) -> None:
        self._scenarios = dict(_DEFAULT_SCENARIOS)
        if scenarios:
            self._scenarios.update(scenarios)

    def render(self, value: RecommendationTemplateInput) -> RenderedRecommendation:
        lines = ["Academic recommendations"]
        if _text(value.student_name):
            lines.append(str(value.student_name))
        lines.extend(["", f"Assessment: {value.data_status}"])
        sections = ["recommendation", "assessment"]
        scenario_names: list[str] = []

        for recommendation in value.recommendations:
            scenario = str(
                recommendation.get("recommendation_type")
                or recommendation.get("category")
                or "recommendation"
            )
            scenario_names.append(scenario)

        evidence = _render_evidence(value.recommendations)
        if evidence:
            sections.append("evidence")
            lines.extend(["", "Verified academic concern", *evidence])

        actions = value.interventions or value.recommendations
        if actions:
            sections.append("interventions")
            lines.extend(["", "Recommended actions (advisory)"])
            for index, action_item in enumerate(actions, start=1):
                action = action_item.get("action")
                if not _text(action):
                    continue
                priority = action_item.get("priority")
                label = f"{priority} priority — " if priority is not None else ""
                lines.append(f"{index}. {label}{str(action).rstrip('.')}")
            sections.append("advisory")
            lines.extend(
                [
                    "",
                    "Advisory note",
                    "These recommendations support tutor decision-making.",
                    "They are not mandatory university policy.",
                ]
            )

        policy = _render_policy(value.recommendations)
        if policy:
            sections.append("policy")
            lines.extend(["", "University policy guidance", *policy])

        if (
            value.data_status == "PARTIAL"
            or value.missing_information
            or value.unavailable_dimensions
        ):
            sections.append("availability")
            availability = _availability_items(value)
            lines.extend(["", "Data availability"])
            if availability:
                lines.append("Some supporting information was unavailable:")
                lines.extend(f"• {item}" for item in availability)
            else:
                lines.append("The requested recommendation could not be fully verified.")

        return RenderedRecommendation(
            text="\n".join(lines),
            sections=tuple(sections),
            scenarios=tuple(scenario_names),
            data_status=value.data_status,
        )


def _render_evidence(
    recommendations: tuple[Mapping[str, Any], ...],
) -> list[str]:
    rendered: list[str] = []
    for recommendation in recommendations:
        evidence = recommendation.get("student_evidence")
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if not isinstance(item, dict):
                continue
            reason = item.get("reason")
            if _text(reason):
                label = f"• {str(reason).rstrip('.')}"
                if label not in rendered:
                    rendered.append(label)
    return rendered


def _render_policy(
    recommendations: tuple[Mapping[str, Any], ...],
) -> list[str]:
    rendered: list[str] = []
    for recommendation in recommendations:
        evidence = recommendation.get("policy_evidence")
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            excerpt = item.get("excerpt")
            if _text(excerpt):
                prefix = f"{source}: " if _text(source) else ""
                line = f"• {prefix}{excerpt}"
                if line not in rendered:
                    rendered.append(line)
    return rendered


def _availability_items(value: RecommendationTemplateInput) -> list[str]:
    rendered: list[str] = []
    for item in value.missing_information:
        label = _missing_information_label(item)
        if label and label not in rendered:
            rendered.append(label)
    for item in value.unavailable_dimensions:
        label = {
            "progress": "Academic progress information",
            "study_right": "Study-right information",
            "academic_events": "Academic event information",
            "tutor_meetings": "Tutor-meeting information",
        }.get(str(item), "Supporting academic information")
        if label not in rendered:
            rendered.append(label)
    return rendered


def _missing_information_label(value: Any) -> str | None:
    if not _text(value):
        return None
    text = str(value).casefold()
    if "policy evidence" in text or "policy context" in text:
        return "University policy guidance"
    if "risk" in text and ("required" in text or "complete" in text):
        return "Verified academic risk assessment"
    if "intervention mapping" in text:
        return "Approved tutor-action guidance"
    return "Supporting recommendation information"


def _append_explanation(
    lines: list[str],
    sections: list[str],
    section_code: str,
    heading: str,
    explanation: Mapping[str, Any] | None,
) -> None:
    if not isinstance(explanation, Mapping):
        return
    summary = explanation.get("summary")
    if not _text(summary):
        return
    sections.append(section_code)
    lines.extend(["", heading, str(summary)])
    warnings = explanation.get("warnings")
    if isinstance(warnings, (list, tuple)):
        lines.extend(f"- {warning}" for warning in warnings if _text(warning))


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
