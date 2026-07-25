# Calendar Agent

The Calendar Agent is responsible for academic calendar queries within the AI Academic Copilot multi-agent architecture.

## Responsibilities

- Receive calendar-related requests for upcoming events, deadlines, tutoring sessions, orientation activities, and exam periods.
- Use the existing MCP event tool `get_upcoming_events` to retrieve structured calendar information.
- Interpret tool responses and return a structured result that other agents or formatters can consume.
- Handle missing or invalid input, tool failures, and empty event sets without crashing.

## Dependencies

- `app.agents.base.AgentResult` for structured agent output.
- `app.agents.types.AgentState` for shared request state.
- `app.mcp.tools.events.get_upcoming_events` for calendar data retrieval.
- `app.core.logger.logger` for consistent project logging.

## Limitations

- The agent does not perform progress analysis, risk detection, reports, or recommendations.
- It relies on the existing MCP event tool and does not query the database directly.
- Student-specific event filtering is limited by the current MCP tool contract.

## Example usage

```python
from app.agents.calendar_agent import CalendarAgent
from app.agents.types import AgentState

agent = CalendarAgent()
state = AgentState(
    request_id="req-123",
    intent="upcoming tutoring events",
    route="calendar",
    student_id=42,
    parameters={"start_date": "2026-09-01", "end_date": "2026-09-30"},
)

result = await agent.run(state)
print(result.data)
```
