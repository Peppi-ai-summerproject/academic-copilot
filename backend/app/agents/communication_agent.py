"""Deterministic tutor-facing response formatting for the Telegram flow."""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState
from app.agents.types import AgentResult


_SOURCE_ORDER = ("progress", "study_rights", "risk", "recommendation", "reporting")
_FACT_ROUTES = ("progress", "study_rights", "risk")


class CommunicationAgent:
    """Format verified workflow results without performing Telegram delivery."""

    name = "CommunicationAgent"
    description = (
        "Formats verified academic results as a concise tutor-facing Telegram "
        "response without sending it."
    )

    async def run(self, state: AgentState) -> AgentResult:
        sources = {
            route: result
            for route in _SOURCE_ORDER
            if isinstance((result := state.agent_results.get(route)), AgentResult)
        }
        usable = {
            route: result
            for route, result in sources.items()
            if result.status != "FAILED" and result.summary.strip()
        }
        report = usable.get("reporting")
        facts = _report_facts(report) if report else [
            usable[route].summary.strip() for route in _FACT_ROUTES if route in usable
        ]
        recommendations = (
            _report_recommendations(report)
            if report
            else _recommendations(usable.get("recommendation"))
        )
        recommendation_presentation = (
            _recommendation_presentation(usable.get("recommendation"))
            if not report
            else None
        )
        incomplete = _is_incomplete(state, sources, usable)

        sections: list[str] = ["summary"]
        lines = [_conclusion(usable, recommendations, incomplete)]
        if facts:
            sections.append("verified_facts")
            lines.extend(["", "Verified facts", *[f"- {fact}" for fact in facts]])
        if recommendation_presentation:
            sections.append("recommendation_presentation")
            lines.extend(["", recommendation_presentation])
        elif recommendations:
            sections.append("recommended_actions")
            lines.extend(["", "Recommended actions (advisory)", *recommendations])
        if incomplete:
            sections.append("warnings")
            lines.extend([
                "",
                "Availability note",
                "- Some requested information could not be verified. Do not treat missing information as confirmation that there is no risk.",
            ])

        message = "\n".join(lines)
        context_used = any(
            value is not None
            for value in (
                state.conversation_id,
                state.telegram_user_id,
                state.telegram_chat_id,
            )
        )
        warning = (
            ["Some requested information was unavailable when the response was formatted."]
            if incomplete
            else []
        )
        return AgentResult(
            agent_name=self.name,
            route="communication",
            status="PARTIAL" if incomplete else "SUCCESS",
            summary=(
                "Tutor-facing response formatted with availability warnings."
                if incomplete
                else "Tutor-facing response formatted."
            ),
            data={
                "conversation_id": state.conversation_id,
                "channel": "telegram",
                "formatted_message": message,
                "sections_included": sections,
                "source_agents": list(usable),
                "context_used": context_used,
                "delivery_status": "NOT_SENT",
            },
            evidence=[f"Formatted verified result from {route}." for route in usable],
            warnings=warning,
        )


def _recommendations(result: AgentResult | None) -> list[str]:
    if result is None:
        return []
    items = result.data.get("recommendations")
    if not isinstance(items, list):
        return []
    formatted: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if not isinstance(action, str) or not action.strip():
            continue
        priority = item.get("priority")
        label = str(priority).upper() if priority else "UNSPECIFIED"
        formatted.append(f"- {label} priority: {action.strip()} (advisory)")
    return formatted


def _recommendation_presentation(result: AgentResult | None) -> str | None:
    if result is None:
        return None
    presentation = result.data.get("rendered_recommendation")
    if not isinstance(presentation, dict):
        return None
    rendered = presentation.get("text")
    return rendered.strip() if isinstance(rendered, str) and rendered.strip() else None


def _report_facts(result: AgentResult) -> list[str]:
    facts: list[str] = []
    for section_name in ("performance", "study_right", "risks"):
        section = result.data.get(section_name)
        if isinstance(section, dict) and isinstance(section.get("summary"), str):
            facts.append(section["summary"].strip())
    return facts


def _report_recommendations(result: AgentResult) -> list[str]:
    section = result.data.get("upcoming_actions")
    items = section.get("items") if isinstance(section, dict) else None
    proxy = AgentResult(
        agent_name="ReportingAgent",
        route="recommendation",
        status=result.status,
        summary=result.summary,
        data={"recommendations": items if isinstance(items, list) else []},
    )
    return _recommendations(proxy)


def _is_incomplete(
    state: AgentState,
    sources: dict[str, AgentResult],
    usable: dict[str, AgentResult],
) -> bool:
    selected_sources = [route for route in state.selected_agents if route != "communication"]
    return (
        not usable
        or any(route not in sources for route in selected_sources)
        or any(result.status != "SUCCESS" for result in sources.values())
    )


def _conclusion(
    usable: dict[str, AgentResult],
    recommendations: list[str],
    incomplete: bool,
) -> str:
    if recommendations:
        return "Tutor summary: Verified findings require review; advisory actions are listed below."
    risk = usable.get("risk")
    if risk is not None and not incomplete:
        return f"Tutor summary: {risk.summary.strip()}"
    if usable:
        return "Tutor summary: Verified academic information is available below."
    return "Tutor summary: Sufficient verified information is unavailable for an academic conclusion."
