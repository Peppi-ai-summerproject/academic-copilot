# Risk Decision Explanations (Issue #113)

## Purpose

Issue #113 makes an existing academic-risk assessment understandable to a
tutor. It explains the canonical score, risk level, contributing indicators,
available evidence, applied overrides, and unavailable indicators.

It does not calculate a score, classify a student, select an intervention, or
explain general academic-progress history.

## Source of truth and flow

`AcademicRiskScoringService.assess_student_risk()` and its pure
`calculate_academic_risk()` function remain the sole owners of risk policy.
`RiskExplanationService` accepts the scorer's already-structured result and
only presents it.

```text
Existing analytics and evidence
        |
AcademicRiskScoringService (#95)
        |
Structured canonical risk result
        |-- score and risk level
        |-- indicator contributions and rule codes
        |-- normalized evidence and authoritative source
        |-- unavailable indicators and overrides
        |
RiskExplanationService (#113)
        |
Tutor-readable explanation in #104 workflow output
```

The explanation service never accepts raw student records and never calls
delay, progress, study-right, tutor-meeting, event, LLM, RAG, or database
services. It therefore cannot recalculate or change a risk decision.

## Explanation contract

For a successful canonical result, `RiskExplanationService` returns:

- the unchanged `risk_score`, `risk_level`, `assessment_status`,
  `score_basis`, and `policy_version`;
- factors ordered by the existing assigned points, each retaining its indicator
  code, assigned and maximum points, rule code, authoritative source, safe
  normalized evidence, and source explanation;
- any canonical overrides and source explanations;
- unavailable indicator codes and explicit warnings for partial assessments;
- a deterministic summary that describes only non-zero contributors as
  risk-increasing.

Zero-point factors remain in the structured `factors` list for transparency,
but the summary does not say that they increased risk.

## Missing data and PARTIAL assessments

Unavailable evidence is preserved exactly as supplied by #95. In particular,
missing tutor-meeting data is never rendered as no tutor meetings or zero risk.

When #95 produces a `PARTIAL` assessment, the explanation says that the named
indicator was unavailable and not treated as zero. If #104 used the approved
`available_indicator_weights` basis, the explanation also states that the
existing score was normalized over available indicator weights. The explanation
does not turn a partial assessment into a complete one or create a missing
score/level.

## Workflow integration and privacy boundary

`AutomaticRiskDetectionWorkflow` (#104) builds the explanation from the same
canonical result that it already parses. At-risk result objects expose it as
`risk_explanation`; no additional risk query or calculation occurs.

The explanation copies only the scorer's normalized evidence. It does not add
student names, course records, meeting notes, Telegram data, credentials, or
new persistence. Consumers should continue applying their own authorization
and delivery policies.

## Determinism and scope

The implementation is deterministic and has no LLM or RAG dependency. RAG is
not a source of truth for a numeric risk decision.

Out of scope for #113:

- recommendation and intervention selection (#111 and #112);
- student-progress explanation (#114);
- changing #95 scoring thresholds, weights, normalization, or overrides;
- replacing the legacy Risk Agent model, changing MCP tools, or redesigning
  LangGraph orchestration.
