# Weekly Workflow and Analytics (Issues #103 and #98)

## Purpose and boundaries

The Weekly Workflow produces one aggregate academic report for the tutor
audience. It is a scheduled orchestrator, not a tutor briefing or delivery
channel.

- Issue #101 owns per-tutor Monday preparation and its unsent briefing payload.
- Issue #103 owns the aggregate weekly report and its approved report storage.
- Issue #105 owns human-readable weekly tutor briefing behavior.
- Issues #106 and #107 own alerts and Telegram delivery.
- Issue #108 remains responsible for general workflow execution logs; the table
  introduced here stores report data, not a generic logging system.

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
status, warnings, non-sensitive error codes, and the Issue #98 `analytics`
object. The current result `schema_version` is `2`.

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

## Weekly analytics contract (Issue #98)

The `analytics` object is the structured, non-identifying weekly academic
analytics report for tutor-facing workflows and future API, reporting, and
agent consumers. It is created by `WeeklyWorkflow.run()` from the existing
sections; it never calls an HTTP endpoint and never recreates progress, delay,
study-right, risk, or Academic Health formulas.

The production wiring calls `EctsAnalyticsService` once for the current
population and calls the canonical `AcademicRiskScoringService` once per valid
student. The canonical risk service is wired with its existing
`TutorMeetingRiskService`. Academic Health is intentionally not included: it
has no weekly historical contract here, and this workflow does not calculate a
second health score.

### Period and population semantics

- `report_period` is `[start_date, end_date)` in the configured IANA timezone.
  The start is the previous Monday at 00:00 and the exclusive end is the
  current Monday at 00:00. The fixed `period_end` date is passed to every
  canonical risk assessment as its `as_of_date`; it is captured once for the
  whole report.
- `population.student_count` is the full set of rows returned by the existing
  paginated `StudentRepository.search_students` contract. This established
  weekly workflow does **not** filter to `ACTIVE`; the separate Issue #104
  automatic risk-detection workflow owns the ACTIVE-only contract.
- Progress is current cumulative ECTS state, not ECTS earned within the
  calendar-week window. The repository does not provide a historical,
  date-filterable completion contract.

### Stable `analytics` structure

```json
{
  "report_period": {
    "start_date": "2026-01-26",
    "end_date": "2026-02-02",
    "end_exclusive": true,
    "timezone": "Europe/Helsinki"
  },
  "population": {"status": "completed", "student_count": 6},
  "progress_statistics": {
    "status": "partial",
    "students_processed": 5,
    "students_unavailable": 1,
    "behind_count": 2,
    "on_track_count": 2,
    "ahead_count": 1,
    "average_completed_ects": 72.5,
    "average_progress_percentage": 80.0
  },
  "risk_summary": {
    "status": "partial",
    "student_population_count": 6,
    "students_assessed": 5,
    "LOW": 1,
    "MEDIUM": 1,
    "HIGH": 1,
    "CRITICAL": 1,
    "PARTIAL": 1,
    "UNAVAILABLE": 1,
    "requires_tutor_attention": 3
  },
  "important_findings": {
    "kind": "CURRENT_WEEKLY_INDICATORS",
    "historical_comparison_available": false,
    "progress_distribution": {"BEHIND": 2, "ON_TRACK": 2, "AHEAD": 1},
    "risk_distribution": {
      "LOW": 1,
      "MEDIUM": 1,
      "HIGH": 1,
      "CRITICAL": 1,
      "PARTIAL": 1,
      "UNAVAILABLE": 1
    }
  },
  "data_quality": {
    "overall_status": "partial",
    "section_statuses": {
      "academic_events": "completed",
      "student_directory": "completed",
      "current_progress": "partial",
      "current_academic_risks": "partial"
    },
    "risk_complete_assessments": 4,
    "risk_partial_assessments": 1,
    "risk_explicitly_unavailable_assessments": 1,
    "risk_failed_assessments": 0
  }
}
```

All values are JSON-serializable. The report contains no student names, IDs,
student numbers, Telegram data, meeting content, or other individual records.

### Progress statistics

`progress_statistics` directly exposes the cohort summary returned by
`EctsAnalyticsService`: successful and unavailable student counts; BEHIND,
ON_TRACK, and AHEAD counts; and averages across successful progress results.
The average denominators are therefore `students_processed`, not the total
population. A missing/unavailable progress section reports `null` statistics
with its section status and reason codes in the enclosing workflow result; it
is never represented as zero.

### Canonical risk summary

`risk_summary` is derived only from `AcademicRiskScoringService` results as of
the report end date. For each student in the report population, exactly one
mutually exclusive bucket is emitted:

- `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` for a `COMPLETE` canonical assessment;
- `PARTIAL` for a valid but incomplete canonical assessment, even if an
  explicit policy layer supplied a normalized partial score;
- `UNAVAILABLE` for a failed, malformed, or explicitly unavailable canonical
  assessment.

Consequently, the six bucket counts always add up to
`student_population_count` when the directory section succeeded. A partial or
unavailable assessment can never be silently downgraded to `LOW`.
`requires_tutor_attention` is the sum of complete `MEDIUM`, `HIGH`, and
`CRITICAL` results. `CRITICAL` remains a distinct field and is never merged or
downgraded. `data_quality` preserves the finer distinction between explicitly
unavailable and failed canonical assessments.

### Important findings and degradation

`important_findings` provides current weekly distributions only. The current
repository has no authoritative historical comparison contract, so
`historical_comparison_available` is always `false` and the report never
claims that progress or risk is improving or worsening.

An empty successful population is a completed report with zero population,
progress, and risk counts. A single progress or risk failure degrades only its
section and the overall workflow status; other aggregate sections still run.
Repository/directory failure makes downstream progress and risk unavailable.
The enclosing `sections`, `warnings`, and `errors` retain reason codes for all
failed or unavailable sources. Consumers must use the status and data-quality
fields instead of assuming a missing metric is a measured zero.

Future consumers may add delivery or API presentation around this stable
aggregate object, but must preserve its period semantics, privacy boundary,
canonical-risk buckets, and incomplete-data handling. They must not infer
student-level information from this aggregate report.

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
