from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.agents.base import AcademicAgent, AgentResult
from app.agents.types import AgentRoute, AgentState
from app.core.logger import logger


class CalendarAgent(AcademicAgent):
    """Agent responsible for academic calendar-related requests."""

    name = "CalendarAgent"
    description = (
        "Retrieves upcoming academic calendar events from existing MCP tools "
        "and returns structured calendar information for the current workflow."
    )
    route: AgentRoute = "calendar"

    async def run(self, state: AgentState) -> AgentResult:
        logger.info(
            "CalendarAgent request received: request_id=%s route=%s student_id=%s",
            state.request_id,
            state.route,
            state.student_id,
        )

        if state.student_id is not None and state.student_id <= 0:
            logger.warning(
                "CalendarAgent invalid student id: %s", state.student_id
            )
            return AgentResult(
                agent_name=self.name,
                route=self.route,
                status="FAILED",
                summary="Invalid student identifier provided.",
                data={"student_id": state.student_id},
                errors=["INVALID_STUDENT_ID"],
            )

        start_date = self._normalize_date_value(
            state.parameters.get("start_date")
        )
        end_date = self._normalize_date_value(state.parameters.get("end_date"))

        if start_date is None and state.parameters.get("date") is not None:
            start_date = self._normalize_date_value(state.parameters.get("date"))
            end_date = start_date

        if start_date is None and state.parameters.get("date_range") is not None:
            range_value = state.parameters["date_range"]
            if isinstance(range_value, dict):
                start_date = start_date or self._normalize_date_value(
                    range_value.get("start_date")
                )
                end_date = end_date or self._normalize_date_value(
                    range_value.get("end_date")
                )
            elif isinstance(range_value, (list, tuple)) and len(range_value) == 2:
                start_date = start_date or self._normalize_date_value(range_value[0])
                end_date = end_date or self._normalize_date_value(range_value[1])

        logger.info(
            "CalendarAgent invoking tool: request_id=%s start_date=%s end_date=%s",
            state.request_id,
            start_date,
            end_date,
        )

        tool_result = self._get_upcoming_events(
            start_date=start_date,
            end_date=end_date,
        )

        if not tool_result.get("success", False):
            logger.error(
                "CalendarAgent tool failure: request_id=%s error=%s message=%s",
                state.request_id,
                tool_result.get("error"),
                tool_result.get("message"),
            )
            return AgentResult(
                agent_name=self.name,
                route=self.route,
                status="FAILED",
                summary="Calendar event retrieval failed.",
                data={
                    "requested_dates": {
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                    "student_id": state.student_id,
                },
                errors=[
                    tool_result.get("error", "UNKNOWN_ERROR"),
                    tool_result.get("message", "An unknown error occurred."),
                ],
            )

        events = self._map_tool_events(tool_result.get("events", []))
        event_count = len(events)

        summary = (
            f"Found {event_count} upcoming calendar event(s)."
            if event_count > 0
            else "No upcoming calendar events were found."
        )

        logger.info(
            "CalendarAgent execution success: request_id=%s event_count=%d",
            state.request_id,
            event_count,
        )

        return AgentResult(
            agent_name=self.name,
            route=self.route,
            status="SUCCESS",
            summary=summary,
            data={
                "filters": tool_result.get("filters", {}),
                "event_count": event_count,
                "events": events,
                "student_id": state.student_id,
            },
            evidence=[
                "Retrieved calendar events using the MCP event tool.",
                f"Requested start_date={start_date}, end_date={end_date}",
            ],
        )

    def _get_upcoming_events(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        from app.mcp.tools.events import get_upcoming_events

        return get_upcoming_events(start_date=start_date, end_date=end_date)

    @staticmethod
    def _normalize_date_value(value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, datetime):
            return value.date().isoformat()

        return None

    @staticmethod
    def _map_tool_events(tool_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": event.get("event_name"),
                "date": event.get("event_date"),
                "type": event.get("event_type"),
                "description": event.get("description"),
                "academic_year": event.get("academic_year"),
                "semester": event.get("semester"),
                "end_date": event.get("end_date"),
                "affects_all_students": event.get("affects_all_students"),
            }
            for event in tool_events
        ]
