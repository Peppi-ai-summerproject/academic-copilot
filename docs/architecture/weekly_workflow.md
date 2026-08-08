# Weekly Workflow (Issue #103)

## Purpose and boundaries

The Weekly Workflow produces one aggregate academic report for the tutor
audience. It is a scheduled orchestrator, not a tutor briefing or delivery
channel.

- Issue #101 owns per-tutor Monday preparation and its unsent briefing payload.
- Issue #103 owns the aggregate weekly report and its approved report storage.
- Issue #105 owns human-readable weekly tutor briefing behavior.
- Issues #106 and #107 own alerts and Telegram delivery.
- Issue #108 records general workflow execution history; the table introduced
  here stores report data, not a generic logging system. See
  [`workflow_execution_logs.md`](workflow_execution_logs.md).

No new academic rules, Tutor entities, or assignment architecture are created.
No Telegram, LLM, Qdrant, MCP tool, queue, Redis, distributed lock, or leader
election is used.

## Schedule and direct execution

When `SCHEDULER_ENABLED=true`, FastAPI registers this job using the existing
Issue #100 in-process scheduler:

- Job ID: `academic_weekly_workflow`
- Day and default time: Monday at `06:00`
- Default timezone: `Europe/Helsinki`
- Configuration: `WEEKLY_WORKFLOW_HOUR`, `WEEKLY_WORKFLOW_MINUTE`, and
  `WEEKLY_WORKFLOW_TIMEZONE`

`WeeklyWorkflow.run(now=...)` is the same entry point used for direct and
scheduled execution. A supplied `now` must be timezone-aware and is converted
to the configured IANA timezone. This allows deterministic tests without
starting FastAPI.

The reporting window is the previous completed calendar week:

```text
[previous Monday 00:00 Europe/Helsinki, current Monday 00:00 Europe/Helsinki)
```

The academic-event source stores dates, so the workflow requests the inclusive
date range from the previous Monday through the preceding Sunday. This maps
exactly to the half-open weekly window for date-only events. IANA timezone
handling covers daylight-saving, month, and year boundaries.

## Report contract

`WeeklyWorkflowResult` is a versioned, typed aggregate result. It includes the
workflow name, deterministic execution key, period boundaries, execution
timestamps, overall status, section results, aggregate metrics, persistence
status, warnings, and non-sensitive error codes.

The execution key is:

```text
weekly:YYYY-MM-DD:YYYY-MM-DD
```

Sections are:

- `academic_events`: events in the completed weekly period;
- `student_directory`: number of rows supplied by the existing directory
  contract (the repository has no authoritative active-student filter);
- `current_progress`: cumulative ECTS/progress summary from
  `EctsAnalyticsService`, not ECTS completed during the week;
- `current_academic_risks`: current-state `AcademicRiskScoringService`
  assessments as of the period end.

The current backend has no date-filterable course-completion contract or
historical risk-event contract. Tutor-meeting evidence exists for current risk
assessment, but the weekly workflow has no historical/date-scoped meeting
metrics. The Academic Health Score exists for per-student dashboard use but is
not historical weekly evidence.
Those unavailable metrics are not represented as zero. A successful empty
source is `completed` with count `0`; unavailable and failed sections use a
null count plus reason codes.

Academic risk assessments can be `partial` because the authoritative
tutor-meeting indicator is not yet available. In that case, risk-level counts
are not inferred from the partial score.

## Persistence, privacy, and limitations

Migration `003_create_weekly_workflow_reports.sql` creates the approved
`weekly_workflow_reports` table. It stores a non-identifying aggregate payload
and execution metadata. The unique `execution_key` prevents duplicate stored
reports for the same reporting period.

This is not a distributed execution lock. Multiple application instances may
still compute the same weekly report, but only one database record is stored.
The stable scheduler job ID prevents duplicate registration only within a
single scheduler instance. A restart can rerun the week; the report table then
returns `already_stored` rather than creating another row.

Do not place student names, IDs, Telegram information, notes, action items,
credentials, or tokens in the report payload or logs. Lifecycle logs contain
only aggregate counts and statuses.

The migration must be applied through the normal database deployment process
before `SCHEDULER_ENABLED=true` is used in an environment. The workflow does
not run migrations or alter production data itself.

## Testing

Focused tests use fakes and a controlled clock. They require no database,
Telegram, Qdrant, LLM, or network connection:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\workflows\test_weekly_workflow.py backend\tests\workflows\test_monday_workflow.py backend\tests\workflows\test_daily_workflow.py backend\tests\test_scheduler.py backend\tests\services\test_ects_analytics_service.py backend\tests\services\test_academic_risk_scoring_service.py
```
