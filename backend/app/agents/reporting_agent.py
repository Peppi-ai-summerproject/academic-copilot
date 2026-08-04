"""Structured tutor reports assembled from verified workflow results."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from app.agents.state import AgentState
from app.agents.types import AgentResult


_EXPECTED_SOURCES = ("progress", "study_rights", "risk", "recommendation")
_SCHEMA_VERSION = "1.0"


class ReportingAgent:
    """Aggregate existing agent results without recalculating academic facts."""

    name = "ReportingAgent"
    description = "Creates an export-ready structured tutor report from verified results."

    async def run(self, state: AgentState) -> AgentResult:
        sources = {
            route: result
            for route in (*_EXPECTED_SOURCES, "calendar")
            if isinstance((result := state.agent_results.get(route)), AgentResult)
        }
        usable = {
            route: result
            for route, result in sources.items()
            if result.status != "FAILED" and isinstance(result.data, dict)
        }

        performance = _performance_section(usable.get("progress"))
        study_right = _study_right_section(usable.get("study_rights"))
        risks = _risk_section(usable.get("risk"))
        actions = _action_section(usable.get("recommendation"))
        events = _event_section(usable.get("calendar"))
        sections = (performance, study_right, risks, actions)
        usable_count = sum(section["status"] == "available" for section in sections)
        complete = usable_count == len(sections) and all(
            sources[route].status == "SUCCESS" for route in _EXPECTED_SOURCES
        )
        overall_status = "complete" if complete else ("partial" if usable_count else "unavailable")
        warnings = _availability_warnings(performance, study_right, risks, actions, events)
        executive_summary = _executive_summary(usable, overall_status)

        report = {
            "report_type": "student_tutor_summary",
            "schema_version": _SCHEMA_VERSION,
            "student_id": state.student_id,
            "overall_status": overall_status,
            "executive_summary": executive_summary,
            "performance": performance,
            "risks": risks,
            "study_right": study_right,
            "upcoming_actions": actions,
            "upcoming_events": events,
            "warnings": warnings,
            "source_agents": [route for route in (*_EXPECTED_SOURCES, "calendar") if route in usable],
            "export": {
                "format": "structured_data",
                "schema_version": _SCHEMA_VERSION,
                "file_generated": False,
            },
        }
        return AgentResult(
            agent_name=self.name,
            route="reporting",
            status="SUCCESS" if complete else "PARTIAL",
            summary=executive_summary,
            data=report,
            evidence=[f"{route} supplied a verified report section." for route in report["source_agents"]],
            warnings=warnings,
        )


def _performance_section(result: AgentResult | None) -> dict[str, Any]:
    fields = (
        "student_name", "programme", "current_semester", "completed_ects",
        "expected_ects", "difference_ects", "progress_percentage", "progress_status",
    )
    return _fact_section(result, fields)


def _study_right_section(result: AgentResult | None) -> dict[str, Any]:
    fields = (
        "study_right_status", "extension_count", "is_expiring_soon",
        "expiration_date", "needs_attention", "urgency", "max_extensions_reached",
    )
    return _fact_section(result, fields)


def _fact_section(result: AgentResult | None, fields: tuple[str, ...]) -> dict[str, Any]:
    if result is None:
        return {"status": "unavailable", "summary": None, "facts": {}, "source_agent": None}
    facts = {key: _json_value(result.data[key]) for key in fields if key in result.data}
    return {
        "status": "available" if facts or result.summary.strip() else "unavailable",
        "summary": result.summary.strip() or None,
        "facts": facts,
        "source_agent": result.route,
    }


def _risk_section(result: AgentResult | None) -> dict[str, Any]:
    if result is None:
        return {"status": "unavailable", "summary": None, "risk_level": None, "items": [], "evidence": [], "source_agent": None}
    items = result.data.get("risk_factors")
    return {
        "status": "available",
        "summary": result.summary.strip() or None,
        "risk_level": _json_value(result.data.get("risk_level")),
        "assessment_complete": bool(result.data.get("assessment_complete")),
        "items": _json_value(items) if isinstance(items, list) else [],
        "evidence": [_json_value(item) for item in result.evidence],
        "source_agent": "risk",
    }


def _action_section(result: AgentResult | None) -> dict[str, Any]:
    if result is None:
        return {"status": "unavailable", "items": [], "source_agent": None}
    raw = result.data.get("recommendations")
    items = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("action"), str):
            continue
        fields = ("priority", "action", "explanation", "source_agents", "deadline", "responsible_actor")
        action = {key: _json_value(item[key]) for key in fields if key in item}
        action["advisory"] = True
        items.append(action)
    return {"status": "available", "items": items, "source_agent": "recommendation"}


def _event_section(result: AgentResult | None) -> dict[str, Any]:
    if result is None:
        return {"status": "unavailable", "items": [], "source_agent": None}
    raw = result.data.get("events")
    return {
        "status": "available" if isinstance(raw, list) else "unavailable",
        "items": _json_value(raw) if isinstance(raw, list) else [],
        "source_agent": "calendar" if isinstance(raw, list) else None,
    }


def _executive_summary(usable: dict[str, AgentResult], status: str) -> str:
    if not usable:
        return "Sufficient verified information is unavailable for a tutor report."
    for route in ("risk", "progress", "study_rights", "recommendation"):
        result = usable.get(route)
        if result is not None and result.summary.strip():
            prefix = "Partial report: " if status != "complete" else ""
            return f"{prefix}{result.summary.strip()}"
    return "Partial report: Verified structured information is available for tutor review."


def _availability_warnings(*sections: dict[str, Any]) -> list[str]:
    labels = ("performance", "study-right", "risk", "recommended-action", "upcoming-event")
    return [
        f"Verified {label} information is unavailable."
        for label, section in zip(labels, sections, strict=True)
        if section["status"] == "unavailable"
    ]


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return None
