# Academic Alerts (Issue #106)

## Purpose and boundaries

Issue #106 normalizes confirmed academic conditions into typed, serializable,
student-linked alerts. It is not a scheduler, persistence layer, delivery
channel, recipient resolver, or conversational agent.

- Issue #93 owns delayed-progress calculation.
- Issue #94 owns study-right qualification and its existing alert codes.
- Issue #104 owns canonical automatic risk evaluation.
- Issue #102 invokes Issue #106 during the existing daily run.
- Issue #107 owns Telegram recipient resolution, formatting, and delivery.
- Issue #108 owns durable workflow-execution history.

No second scheduled job is registered. The existing Issue #100 scheduler runs
Issue #102 once daily when scheduling is enabled.

## Supported alert types

| Alert type | Qualification source | Severity | Student linkage |
| --- | --- | --- | --- |
| `DELAYED_PROGRESS` | `DelayDetectionService.detect_student_delay()` returns `is_delayed = true` | None: #93 defines no standalone alert severity | Canonical `student_id` |
| `STUDY_RIGHT_EXPIRED` | Existing #94 structured `risk.alert` payload | None: the preserved #94 `risk_status` remains evidence, not a new severity mapping | Canonical `student_id` |
| `STUDY_RIGHT_EXPIRING_SOON` | Existing #94 structured `risk.alert` payload | None | Canonical `student_id` |
| `STUDY_RIGHT_EXTENDED` | Existing #94 structured `risk.alert` payload | None | Canonical `student_id` |
| `ACADEMIC_RISK_DETECTED` | #104 `StudentRiskDetectionResult` requiring tutor attention | Exact canonical #104 risk level | Canonical `student_id` |

Study-right alerts reuse #94's already-qualified `alert_code`; #106 neither
changes its status rules nor creates a new expiry threshold. Delayed-progress
alerts preserve #93's existing any-deficit condition and do not assign an
invented severity.

An overall-risk alert is suppressed when an already-generated specific alert
covers one of its `actionable_indicators` (`academic_delay` or `study_right`).
This avoids duplicate alert records for the same confirmed condition. Overall
risk can still be emitted when no specific alert covers a canonical attention
result.

## Deferred event alerts

Issue #106 creates no direct academic-event alert type. The current event
contract has no alert urgency policy, cancellation state, student/cohort scope,
or delivery window. Event information may remain evidence inside a canonical
overall-risk result, but it is not independently converted to an alert.

## Contracts and source availability

`AcademicAlertWorkflow.run(evaluation_time=..., risk_detection_result=...)`
collects #93 and #94 results only for canonical ACTIVE students, then delegates
to the pure `AcademicAlertGenerator`. The #104 result is supplied by #102's
existing daily execution; it is not recalculated by #106.

`AcademicAlertGenerationResult` includes an overall `completed`, `partial`, or
`failed` status, source statuses, non-sensitive error codes, deterministic
alerts, type counts, and the count of suppressed generic risk alerts. An empty
ACTIVE scope is `completed` with zero alerts. A missing source is never treated
as no alert or low risk; usable sources can still yield a `partial` result.

Each `AcademicAlert` contains a machine-readable type, `affected_student_id`,
source, optional canonical severity, minimal source evidence, and an optional
occurrence date. It contains no ORM object, student name, student number,
email, Telegram identifier, recipient, or delivery metadata.

## Delivery, persistence, and lifecycle limits

Alert generation is usable without FastAPI startup, scheduler startup,
Telegram, LLM, RAG, Qdrant, external network access, or a real database when
test fakes are supplied. It makes no Telegram call and requires no token.

Alerts are returned in memory only. No alert table, repository, lifecycle,
acknowledgement, resolution, delivery history, fingerprint, or deduplication
guarantee exists. Repeated daily runs or multiple application instances can
return the same alert again. Logs remain aggregate-only and must not contain
student identifiers or full alert payloads.

## Testing

Focused tests use fakes and a controlled Helsinki clock:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\workflows\test_academic_alerts.py backend\tests\workflows\test_daily_workflow.py backend\tests\workflows\test_automatic_risk_detection.py
```
