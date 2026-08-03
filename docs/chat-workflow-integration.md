# Chat Service Workflow Integration

`ChatService` is the application-layer entry point for academic workflow runs.
An API caller opts into the workflow by sending one or more explicit
`selected_agents` values and may provide a `student_id`.

The service creates the canonical `AgentState`, copies the request and Telegram
context into it, invokes `AcademicAgentWorkflow`, and formats agent summaries in
the same order as `selected_agents`. Requests without selected agents retain the
existing non-workflow response.

The service does not infer intent and does not access agents, MCP tools,
repositories, or database sessions directly. Both the workflow and session
service are constructor-injected so integration tests can use in-memory fakes.

Example request:

```json
{
  "message": "Check this student's progress",
  "telegram_user_id": 101,
  "telegram_chat_id": 202,
  "username": "tutor",
  "student_id": 42,
  "selected_agents": ["progress", "study_rights"]
}
```
