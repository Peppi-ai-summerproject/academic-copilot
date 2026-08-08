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
        lines = ["Recommendation"]
        sections = ["recommendation"]
        scenario_names: list[str] = []

        for recommendation in value.recommendations:
            scenario = str(
                recommendation.get("recommendation_type")
                or recommendation.get("category")
                or "recommendation"
            )
            scenario_names.append(scenario)
            template = self._scenarios.get(
                scenario,
                ScenarioTemplate("Tutor recommendation", "Situation"),
            )
            lines.extend(["", template.title])
            priority = recommendation.get("priority")
            if priority is not None:
                lines.append(f"Priority: {priority}")
            explanation = recommendation.get("explanation")
            if _text(explanation):
                lines.append(f"{template.situation_label}: {explanation}")
            action = recommendation.get("action")
            if _text(action):
                lines.append(f"Recommended action: {action}")

        evidence = _render_evidence(value.recommendations)
        if evidence:
            sections.append("evidence")
            lines.extend(["", "Supporting evidence", *evidence])

        if value.interventions:
            sections.append("interventions")
            lines.extend(["", "Recommended actions (advisory)"])
            for index, intervention in enumerate(value.interventions, start=1):
                action = intervention.get("action")
                if not _text(action):
                    continue
                priority = intervention.get("priority")
                label = f"{priority} priority: " if priority is not None else ""
                lines.append(f"{index}. {label}{action} (advisory)")

        _append_explanation(
            lines,
            sections,
            "risk_explanation",
            "Risk explanation",
            value.risk_explanation,
        )
        _append_explanation(
            lines,
            sections,
            "progress_explanation",
            "Progress explanation",
            value.progress_explanation,
        )

        policy = _render_policy(value.recommendations)
        if policy:
            sections.append("policy")
            lines.extend(["", "Relevant guidance", *policy])

        if (
            value.data_status == "PARTIAL"
            or value.missing_information
            or value.unavailable_dimensions
        ):
            sections.append("availability")
            lines.extend(["", "Data availability", f"Status: {value.data_status}"])
            lines.extend(f"- {item}" for item in value.missing_information if _text(item))
            lines.extend(
                f"- Unavailable: {item}"
                for item in value.unavailable_dimensions
                if _text(item)
            )

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
            source = item.get("source_agent")
            values = item.get("values")
            parts = [str(reason)] if _text(reason) else []
            if isinstance(values, dict) and values:
                parts.append(", ".join(f"{key}={value}" for key, value in values.items()))
            if parts:
                prefix = f"{source}: " if _text(source) else ""
                rendered.append(f"- {prefix}{'; '.join(parts)}")
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
                rendered.append(f"- {prefix}{excerpt}")
    return rendered


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
