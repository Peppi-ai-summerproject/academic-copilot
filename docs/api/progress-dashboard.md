# Progress Dashboard API (Issue #97)

## Endpoint

`GET /api/v1/students/{student_id}/progress-dashboard`

Returns the existing `StudentDashboardService` response for one student. It is
intended for dashboard clients, AI agents, and service integrations that need a
single, consistent view of current academic analytics.

### Parameters

| Parameter | Location | Required | Meaning |
| --- | --- | --- | --- |
| `student_id` | path | yes | Positive canonical numeric student ID. |
| `as_of_date` | query | no | ISO-8601 effective date for date-sensitive analytics. |

When `as_of_date` is omitted, the dashboard service captures the current date
once for the request. The route forwards the provided date unchanged and does
not perform separate date-sensitive analytics itself.

## Response

A successful response is the JSON-serializable dashboard contract:

```json
{
  "success": true,
  "student_id": 1,
  "dashboard": {
    "profile": {},
    "academic_progress": {
      "completed_ects": 90,
      "expected_ects": 120,
      "difference_ects": -30,
      "progress_percentage": 75.0,
      "status": "BEHIND"
    },
    "study_right": {},
    "academic_health": {},
    "risk": {
      "current_analysis": {},
      "supporting_legacy_analysis": {}
    },
    "upcoming_actions": {},
    "summary": {}
  }
}
```

The exact section semantics are owned by `StudentDashboardService`. The API
does not recalculate progress, delay, study-right, event, risk, or Health
values. Its request-scoped dependency wiring memoizes shared source reads, so
the dashboard and canonical risk assessment reuse overlapping evidence.

## Risk and Academic Health

`risk.current_analysis` is the canonical Issue #95 assessment. Academic Health
is the existing Issue #96 result derived from that same assessment. The route
does not create an independent scoring path.

The response preserves the dashboard priority contract:

| Canonical state | `summary.priority` | Attention required |
| --- | --- | --- |
| COMPLETE / CRITICAL or HIGH | HIGH | yes |
| COMPLETE / MEDIUM | MEDIUM | yes |
| COMPLETE / LOW | LOW | normally no |
| PARTIAL without authoritative level | UNKNOWN | yes |
| UNAVAILABLE or unsupported level | UNKNOWN | yes |

`supporting_legacy_analysis` remains explicitly non-authoritative and must not
be substituted for canonical risk. PARTIAL or UNAVAILABLE results never become
LOW merely because supporting legacy analytics are available.

## Errors

- Invalid non-positive `student_id`: FastAPI returns `422` before the service
  is invoked.
- Unknown student: `404` with a safe not-found detail.
- Unexpected service failure: `500` with a generic message; implementation
  details and stack traces are not returned.

Optional analytics failures are represented by the established dashboard
PARTIAL/UNAVAILABLE sections whenever the dashboard service can still produce
a response.

## Compatibility

This is an additive HTTP surface over the existing dashboard contract. Clients
should inspect `assessment_status`, `risk.current_analysis.source`, and
`summary.priority` rather than assuming that a missing or partial canonical
assessment is low risk.
