# Monday Workflow (Issue #101)

## Purpose

The Monday Workflow prepares one structured weekly briefing for each active
tutor teacher. It is an application-level orchestrator: it reads current tutor
assignments, calls existing progress and risk services, includes relevant
academic events, and produces an unsent Telegram-ready payload.

It does not calculate ECTS or risk formulas, send Telegram messages, create a
second scheduler, or persist workflow execution logs.

## Schedule

When `SCHEDULER_ENABLED=true`, FastAPI registers one job with ID
`monday_workflow` on the existing scheduler. The job uses
`DailyTimeTrigger(days_of_week={0})`, where `0` is Monday.

- Time: `MONDAY_WORKFLOW_HOUR` and `MONDAY_WORKFLOW_MINUTE` (default `06:00`)
- Timezone: `SCHEDULER_TIMEZONE` (default `UTC`)
- Duplicate registration: ignored within one scheduler instance

The scheduler is disabled by default, so tests and local development do not
start background jobs unless explicitly enabled.

## Data dependencies

The workflow consumes:

- `tutors` and `tutor_student_assignments` for tutor discovery;
- `ProgressService` for completed and expected ECTS;
- `AcademicRiskScoringService` for existing structured risk indicators;
- `EventService` for the Monday-to-Sunday academic-event window.

Apply `backend/db/migrations/002_create_tutor_assignments.sql` to the existing
PostgreSQL database before enabling the scheduled workflow. The migration adds
the tutor destination fields and the current tutor-to-student mapping; it does
not add student records or populate assignments.

## Result contract

`MondayWorkflow.run()` is directly invocable and returns a typed result with:

- execution status: `completed`, `partial`, or `failed`;
- a timezone-aware generation timestamp and Monday-to-Sunday period;
- one `MondayTutorBriefing` per active tutor;
- summary counts, priority students ordered by existing risk output, events,
  and availability warnings;
- a Telegram payload with `delivery_status` of `NOT_SENT` or `NO_DESTINATION`.

The workflow does not call the Telegram Bot API. Delivery and retry behavior
remain deferred to Issue #107.

## Failure and duplicate-execution behavior

- No tutors or no assigned students is a valid completed result.
- Missing destinations and partial student analysis produce warnings.
- If every assigned student's analytics are unavailable, the result is failed.
- The stable job ID prevents duplicate registration in one process only.
- Restarts and multiple application instances are not deduplicated; persistent
  execution records and cross-process idempotency remain deferred to Issue #108.

## Tests

Run the focused workflow and scheduler checks:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\workflows\test_monday_workflow.py backend\tests\test_scheduler.py
```
