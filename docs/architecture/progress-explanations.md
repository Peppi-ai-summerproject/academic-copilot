# Progress explanations

Issue #114 adds a deterministic explanation layer for academic progress. The
layer explains the result already returned by `ProgressService.get_progress`;
it does not query data or calculate, classify, predict, or recommend anything.

## Data flow

`ProgressAnalysisAgent` passes the complete `get_progress` response to
`ProgressExplanationService`. The resulting `progress_explanation` is stored
inside the agent result's `data` object alongside the existing progress fields.
This keeps the existing agent route, status mapping, summary, and shared state
contract unchanged.

Each available indicator contains its original value, its role in the progress
result, and a stable source reference such as `get_progress.completed_ects`.
The explanation repeats the upstream values verbatim. In particular, it does
not subtract ECTS values, calculate percentages, or infer a status.

## Meaning of the inputs

- `completed_ects` is the sum of credits in the student's course completions.
- `current_semester` is the highest semester in those completions, defaulting
  to semester 1 in the progress repository.
- `expected_ects` is the curriculum milestone for that programme and semester.
- `difference_ects`, `remaining_to_expected_ects`, `progress_percentage`, and
  `status` are calculations supplied by `ProgressService`.

Expected ECTS therefore describes a curriculum milestone, not elapsed calendar
time or an individualized study-right schedule. The existing classification has
no tolerance band: a deficit is `BEHIND`, equality is `ON_TRACK`, and a surplus
is `AHEAD`.

## Missing data

When progress retrieval fails, or a required progress field is absent, the
explanation is marked `PARTIAL`. Missing fields remain `null`, are listed in
`unavailable_fields`, and are never replaced with zero or derived from other
values. Upstream error codes are retained as warnings.

The explanation contains no risk score, intervention, or recommendation. Those
remain responsibilities of their existing dedicated services and agents.
