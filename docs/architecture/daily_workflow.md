# Daily Workflow (Issue #102)

## Purpose

The Daily Workflow is a deterministic application-level orchestrator. It checks
academic events for the local calendar day and invokes the existing academic
risk service for every student returned by the existing student-directory
contract. It does not create academic rules, make LLM decisions, persist
executions, or interpret tutor-meeting free text. When the Telegram application
is enabled, it hands the exact structured Issue #106 result to Issue #107.

## Schedule and configuration

When `SCHEDULER_ENABLED=true`, FastAPI registers one recurring job on the
Issue #100 scheduler.

- Job ID: `academic_daily_workflow`
- Default time: `06:00`
- Default timezone: `Europe/Helsinki`
- Configuration: `DAILY_WORKFLOW_HOUR`, `DAILY_WORKFLOW_MINUTE`, and
  `DAILY_WORKFLOW_TIMEZONE`

The daily workflow has its own timezone setting. This avoids changing the
existing scheduler and Monday-workflow defaults. `Europe/Helsinki` is an IANA
timezone, so daylight-saving changes are handled correctly.

The scheduler remains disabled by default. Set `SCHEDULER_ENABLED=true` in the
runtime environment only after the workflow is configured for that deployment.

## Daily period and direct execution

`DailyWorkflow.run(now=...)` is directly invocable. A supplied `now` must be
timezone-aware; it is converted to the configured daily timezone.

The execution date is the local calendar date and uses the diagnostic key:

```text
daily:YYYY-MM-DD
```

Academic events use the inclusive date range from that local date to the same
local date. Since the current academic-event contract stores dates rather than
times, this means events occurring on that calendar day.

Risk checks pass the same local date to Issue #104's reusable
`AutomaticRiskDetectionWorkflow`. That workflow uses the canonical
`StudentRepository.list_active_student_ids()` contract and evaluates only
students with `status = ACTIVE`. It does not infer activity from study-right
dates, missing records, or any other indirect signal.

## Result contract

`DailyWorkflowResult` contains an aggregate workflow status and one typed
`DailyCheckResult` for each check:

- `academic_events`
- `student_risks`
- `academic_alerts`
- `tutor_notifications`
- `pending_tutor_actions`

Check statuses are `completed`, `partial`, `failed`, or `unavailable`.

- A completed event or risk check with no items has `count: 0`.
- An unavailable or failed check has `count: null`, never zero.
- A risk result whose authoritative assessment is partial makes the aggregate
  risk check partial. Issue #104 may supply a normalized canonical level, but
  the partial status and unavailable indicators remain explicit.
- Issue #106 receives the exact #104 result already evaluated by this run and
  generates structured, non-persistent alerts from established #93 and #94
  sources. It does not add a scheduler or create event-reminder alerts.
- Issue #107 receives that same in-memory #106 result immediately after
  generation. It resolves only administrator-provisioned active Tutor mappings
  and reports aggregate delivery counts. Delivery is unavailable, rather than
  silently skipped as success, when the Telegram application is not enabled.
- The overall workflow is completed only when all checks complete. It is partial
  when one useful check completes while another is partial, failed, or
  unavailable.

## Tutor-action limitation

There is no structured tutor-action domain contract in the current backend:
there is no repository/model with status, assignee, due date, or completion
state. The workflow therefore returns:

```text
pending_tutor_actions.status = unavailable
pending_tutor_actions.reason_codes = [TUTOR_ACTION_CONTRACT_UNAVAILABLE]
```

It does not read or infer actions from free-text `tutor_meetings.action_items`.
Until a future issue establishes that domain, a normal daily run will be
`partial` even when event and risk checks complete.

## Logging and idempotency limits

The workflow uses the existing application logger and records only lifecycle,
status, and aggregate count information. It does not log student names, IDs,
Telegram details, credentials, tokens, or full result payloads.

Issue #108 records durable aggregate execution history for the daily run and
its nested #104, #106, and #107 calls. It does not persist alert payloads,
individual delivery attempts, recipients, or rendered Telegram messages. See
[`workflow_execution_logs.md`](workflow_execution_logs.md) for lifecycle,
privacy, and reliability limits.

The stable job ID prevents duplicate registration in a single scheduler
instance. It does not prevent a same-day rerun after restart, or duplicate
execution by multiple backend instances. No Redis, queue, distributed lock, or
leader election is used.

## Testing

Focused tests use injected dependencies and a controlled clock; they do not
need Telegram, Qdrant, an LLM, a database, or network access.

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\workflows\test_daily_workflow.py backend\tests\test_scheduler.py backend\tests\test_event_service.py backend\tests\services\test_academic_risk_scoring_service.py
```

The tests cover registration, duplicate protection, configured Helsinki time,
calendar boundaries, direct invocation, zero-item results, unavailable data,
partial and total failure, lifecycle shutdown, and aggregate-only logging.

## Deferred responsibilities

This workflow does not implement tutor actions, delivery history, RAG,
MCP tools, LLM decisions, new risk rules, database migrations, queues, or
distributed coordination. It invokes Issue #106 but does not own alert
qualification, alert persistence, Telegram rendering, recipient resolution,
provider acknowledgement, or resolution. Those responsibilities remain with
Issue #107 and future delivery-history work.
