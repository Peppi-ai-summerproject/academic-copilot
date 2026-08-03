# Academic Tool Gateway

The `AcademicToolGateway` is the application boundary between academic agents
and the existing MCP tool ecosystem. Agents must depend on the gateway protocol
instead of creating database sessions, repositories, or services.

`MCPAcademicToolGateway` is the initial in-process adapter. It delegates to the
existing MCP-compatible tool functions and runs their synchronous database work
outside the async workflow event loop. The callables are injectable, allowing
agent and workflow tests to use deterministic fakes without a database or MCP
transport.

The first contract intentionally contains only the operations required by the
existing agents:

- `get_student(student_id)`
- `get_progress(student_id)`
- `get_study_right(student_id)`

Structured tool failures such as `{"success": false, ...}` pass through unchanged
for agents to interpret. A malformed non-dictionary tool response raises
`AcademicToolGatewayError`.

Migrating the existing agents to receive this gateway through dependency
injection is handled separately in Issue #166.
