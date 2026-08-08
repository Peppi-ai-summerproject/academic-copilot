# Academic Health Score

The Academic Health Score is a deterministic, dashboard-ready view of a
student's current academic standing. It is not a clinical assessment,
prediction, or diagnosis.

## Relationship to academic risk

Academic risk and academic health use opposite directions:

- Academic Risk Score: 0–100, where higher means greater risk.
- Academic Health Score: 0–100, where higher means healthier standing.

The dashboard evaluates one canonical Issue #95 assessment and supplies that
same result to both its authoritative risk presentation and the health
converter. The health service
calculates `health_score = 100 - risk_score`. It never recalculates ECTS,
study-right policy, tutor-meeting policy, academic-event applicability, risk
weights, thresholds, or overrides. This inverse is meaningful because the
canonical risk indicators have stable weights totaling 100.

## Inputs and weights

| Canonical indicator | Maximum weight |
| --- | ---: |
| Academic delay against expected ECTS | 50 |
| Study-right status | 30 |
| Tutor-meeting evidence | 10 |
| Applicable academic deadlines | 10 |

Each component exposes both `risk_points` and `health_points`, where
`health_points = maximum_points - risk_points`. Canonical risk overrides remain
explicit health adjustments. For example, the expired-study-right risk floor
may reduce health below the unadjusted component total.

## Interpretation

The bands exactly invert the canonical risk thresholds, preventing conflicting
interpretations of the two scores.

| Health score | Health level | Corresponding risk band |
| ---: | --- | --- |
| 81–100 | `STRONG` | `LOW` (risk 0–19) |
| 61–80 | `STABLE` | `MEDIUM` (risk 20–39) |
| 31–60 | `NEEDS_ATTENTION` | `HIGH` (risk 40–69) |
| 0–30 | `URGENT_SUPPORT` | `CRITICAL` (risk 70–100) |

## Missing data

The default Issue #95 contract does not publish an overall score when evidence
is incomplete. Academic health preserves that rule:

- `assessment_status` is `PARTIAL`;
- `health_score` and `health_level` are null;
- verified components remain visible;
- `missing_indicators` lists unavailable evidence;
- the result is never normalized from only the available weights.

Issue #95 can explicitly produce a normalized numeric risk score for PARTIAL
evidence with `allow_partial_risk_level=True`. Academic Health deliberately
does not complement that opt-in partial score: health remains `PARTIAL` with a
null `health_score` and `health_level`. This prevents incomplete evidence from
being presented as an authoritative health measure.

Malformed or unavailable canonical risk results are `UNPROCESSABLE` and never
default to healthy or unhealthy.

Academic Health accepts only the current `academic-risk-v1` canonical envelope.
For a COMPLETE assessment, the canonical score must reconcile with the
component points and any canonical override, and its risk level must be the
level returned by the Issue #95 classifier for that score. A PARTIAL result may
have either no score/level or the existing opt-in normalized score/level pair;
in both cases Health remains null. This validation detects contradictory input
without recalculating academic risk.

## Example

A student with 15 academic-delay risk points, 20 study-right risk points,
5 tutor-meeting risk points, and 0 event risk points has risk 40 and health 60:

```text
risk = 15 + 20 + 5 + 0 = 40
health = 100 - 40 = 60 (NEEDS_ATTENTION)
```

## Dashboard contract

`StudentDashboardService` adds an `academic_health` sibling section while
preserving all existing dashboard sections. `risk.current_analysis` is the
canonical Issue #95 assessment used for Health. The former progress/study-right
heuristic remains only as `risk.supporting_legacy_analysis`, is explicitly
scoped, and is marked as non-authoritative. Business logic remains in the
analytics services; the dashboard only orchestrates and presents their results.

One effective assessment date is captured at the start of each dashboard
request. The same date is supplied to canonical risk (including its
study-right, tutor-meeting, and academic-event evaluation) and to the dashboard
event window. Callers may provide `as_of_date`; otherwise the dashboard captures
the current local date once.

```json
{
  "academic_health": {
    "success": true,
    "student_id": 1,
    "assessment_status": "COMPLETE",
    "health_score": 60,
    "health_level": "NEEDS_ATTENTION",
    "score_direction": "HIGHER_IS_HEALTHIER",
    "components": [],
    "missing_indicators": [],
    "adjustments": [],
    "policy_version": "academic-health-v1",
    "source_risk_policy_version": "academic-risk-v1"
  }
}
```

The MCP dashboard construction injects the health service and canonical risk
scorer. Request-scoped memoization lets the dashboard sections and risk scorer
reuse overlapping student, progress, study-right, and event evidence without
repeating repository reads. Routes and response mappers contain no scoring
formula.

Each MCP request constructs fresh service instances and fresh memoization
caches. Nothing is shared between students, requests, or concurrent callers.
Cache keys retain the complete method arguments. Exceptions are not cached;
the owning dashboard/service degradation policy handles them. Non-successful
results may be reused within the same request exactly as returned and are never
upgraded to successful or more complete evidence.

If canonical risk is not injected or cannot be evaluated, the compatibility
fallback is explicit:

```json
{
  "risk": {
    "current_analysis": {
      "risk_level": null,
      "score": null,
      "assessment_status": "UNAVAILABLE",
      "source": "LEGACY_PROGRESS_STUDY_RIGHT_FALLBACK"
    },
    "supporting_legacy_analysis": {
      "scope": "PROGRESS_AND_STUDY_RIGHT_ONLY",
      "authoritative_overall_risk": false
    }
  },
  "academic_health": {
    "assessment_status": "UNAVAILABLE",
    "health_score": null,
    "health_level": null
  }
}
```

The heuristic level appears only inside `supporting_legacy_analysis`; it is
never substituted into the canonical `current_analysis.risk_level` field.
Canonical-unavailable `current_analysis.reasons` describes only that
unavailability; legacy levels and explanations remain exclusively in
`supporting_legacy_analysis`. Missing services, raised failures, and returned
unsuccessful canonical results all produce the same `UNAVAILABLE` Health with a
null score and level. The fallback source label identifies the compatibility
path and does not make its legacy heuristic authoritative.

If the Health converter rejects a risk envelope as malformed, the dashboard
also treats that envelope as unavailable rather than presenting its raw score
or level as authoritative. This reuses the converter's canonical validation;
the dashboard does not implement a second risk validator or scoring model.

Canonical `CRITICAL` risk maps to the dashboard's highest available summary
priority (`HIGH`) with attention required. This is presentation mapping only;
the dashboard does not reclassify or rescore canonical risk.

Dashboard summary priority uses this presentation mapping:

| Canonical assessment | Summary priority | Attention required |
| --- | --- | --- |
| COMPLETE / `CRITICAL` | `HIGH` | yes |
| COMPLETE / `HIGH` | `HIGH` | yes |
| COMPLETE / `MEDIUM` | `MEDIUM` | yes |
| COMPLETE / `LOW` | `LOW` | no, unless another dashboard finding requires attention |
| PARTIAL with no authoritative level | `UNKNOWN` | yes |
| UNAVAILABLE | `UNKNOWN` | yes |
| Unsupported or unknown level | `UNKNOWN` | yes |

For `PARTIAL`, `UNAVAILABLE`, and unsupported levels, the summary explicitly
states that authoritative priority is indeterminate. Incomplete or unavailable
evidence is never summarized as `LOW`. The non-authoritative legacy level and
reasons remain supporting context and do not determine canonical dashboard
priority. This mapping is presentation policy, not a second risk score or risk
classification model.

Issue #96 is an additive JSON change, but it intentionally clarifies the
semantics of `risk.current_analysis`. Strict-key consumers must allow the new
`academic_health`, canonical risk metadata, and `supporting_legacy_analysis`
fields, and consumers should use `source` and `assessment_status` when deciding
whether canonical overall risk is available.
