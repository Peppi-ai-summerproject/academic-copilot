# Academic Risk Scoring Model (Issue #95)

Policy version: `academic-risk-v1`

The model is deterministic. Higher scores mean higher academic risk. The
theoretical range is 0–100 and the final score is the sum of verified indicator
contributions, except for the expired-study-right override documented below.
No LLM, RAG system, repository, API, agent, or dashboard owns or duplicates
these scoring rules.

## Authoritative inputs

The model consumes the structured `delay` result from Issue #93 and the
structured `risk` result from Issue #94. It does not recalculate completed or
expected ECTS, academic delay, expiration dates, or study-right classification.

Academic-event facts come from `EventService` and `EventRepository`. The
existing `affects_all_students` boolean is treated as the structured statement
that an event applies to every student. Event names and descriptions are never
used to infer applicability or deadline type.

Tutor-meeting facts come from `TutorMeetingRiskService` and
`TutorMeetingRepository`. Meeting timestamps are normalized to UTC calendar
dates and evaluated against the caller-supplied `as_of_date`: an inclusive
90-day completed/missed lookback and inclusive 30-day scheduled window.
Supported statuses are `SCHEDULED`, `COMPLETED`, `MISSED`, and `CANCELLED`.

Issue #104 may explicitly opt into `allow_partial_risk_level=True`. Only in
that mode, the scorer normalizes verified contribution points against the sum
of verified available indicator maxima, then maps the normalized 0â€“100 score
through the same canonical levels below. The result remains `PARTIAL` and
lists every unavailable indicator. This does not treat unavailable data as a
zero-point or safe condition. The default remains strict: a partial assessment
has no final score or risk level.

## Contributions

| Indicator | Verified condition | Points | Maximum |
|---|---|---:|---:|
| Academic delay | Not delayed / 0 ECTS delayed | 0 | 50 |
| Academic delay | 1–29 ECTS delayed | 15 | 50 |
| Academic delay | 30–59 ECTS delayed | 30 | 50 |
| Academic delay | At least 60 ECTS delayed | 50 | 50 |
| Study right | `SAFE` | 0 | 30 |
| Study right | `EXTENDED` | 0 | 30 |
| Study right | `EXPIRING_SOON` | 20 | 30 |
| Study right | `EXPIRED` | 30 | 30 |
| Academic events | No applicable deadline from day 0 through day 14 | 0 | 10 |
| Academic events | One or more applicable deadlines from day 0 through day 14 | 10 total | 10 |
| Tutor meetings | Recent completed meeting with no later miss | 0 | 10 |
| Tutor meetings | Upcoming scheduled meeting without decisive recent history | 5 | 10 |
| Tutor meetings | Recent missed meeting with no later completion | 10 | 10 |

A later `COMPLETED` meeting supersedes an earlier `MISSED` meeting; a later
`MISSED` meeting supersedes an older completion. `CANCELLED` meetings do not
contribute, and an overdue `SCHEDULED` meeting is never inferred to be missed.
Cancelled-only, empty, malformed, unsupported, or failed evidence remains
unavailable rather than contributing zero.

An authoritative `EXPIRED` study right applies the
`STUDY_RIGHT_EXPIRED` override: `score = max(raw_subtotal, 70)`. Both the raw
subtotal and override details are returned.

## Risk levels

| Score | Level |
|---:|---|
| 0–19 | `LOW` |
| 20–39 | `MEDIUM` |
| 40–69 | `HIGH` |
| 70–100 | `CRITICAL` |

All boundaries are inclusive and have no gaps or overlaps.

## Availability and validation

- `COMPLETE`: all four indicators were authoritatively evaluated. The result
  contains a final score and risk level.
- `PARTIAL`: #93 and #94 are valid, but a secondary indicator is unavailable.
  By default, `score` and `risk_level` are null. An explicit Issue #104
  opt-in can return a normalized canonical score and level, with
  `score_basis = available_indicator_weights`; it is still not a complete
  evaluation.
- `UNPROCESSABLE`: #93 or #94 failed, is missing, malformed, contradictory, or
  unsupported, or mandatory request data is invalid. Score, subtotal, and risk
  level are null.

Missing evidence never contributes zero. A zero contribution is returned only
when a successful authoritative evaluation proves the corresponding no-risk
condition. Machine-readable rule, indicator, override, status, and policy codes
are authoritative; explanations are supplemental.

## Output

The serializable result contains `success`, `student_id`, `as_of_date`,
`assessment_status`, `score`, `raw_subtotal`, `available_indicator_maximum`,
`score_basis`, `score_range`, `score_direction`, `risk_level`, ordered
`indicator_contributions`, `unavailable_indicators`, `applied_overrides`,
`explanation`, and `policy_version`.

Each contribution records its indicator code, authoritative source, normalized
input, matched rule code, assigned points, maximum points, and explanation.
