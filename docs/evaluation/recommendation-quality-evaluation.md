# Recommendation Quality Evaluation

## 1. Scope

This evaluation assesses the recommendation system delivered by Epic #109,
Issues #110–#115. It evaluates actual deterministic decisions, interventions,
evidence, explanations, policy enrichment and tutor-facing templates. It does
not change production rules or use an LLM as a judge.

## 2. System under evaluation

The tested agent path is:

```text
structured risk factors
  -> RecommendationEngine
  -> InterventionSuggestionService
  -> RecommendationAgent policy enrichment
  -> RecommendationTemplateService
  -> tutor-facing presentation
```

`ProgressExplanationService` and `RiskExplanationService` are evaluated against
their canonical contracts. The LangGraph `RiskDetectionAgent` uses the simpler
`risk_policy.py` path, while canonical #95 scoring and #113 explanation are
integrated into the separate automatic-risk workflow. Consequently, ordinary
LangGraph recommendations do not currently receive #113 explanations.

## 3. Evaluation method

Ten predefined synthetic academic scenarios exercise real project rules. The
evaluation combines 21 deterministic assertions with a structured qualitative
review. Policy retrieval is replaced by a deterministic gateway returning a
known candidate or a controlled unavailable result. No live database, RAG
service, external API or LLM is involved.

The reproducible scenarios are defined in
`backend/tests/evaluation/recommendation_scenarios.py`. Run them with:

```bash
DEBUG=false PYTHONPATH=backend:. python -m pytest -q \
  backend/tests/evaluation/test_recommendation_quality.py
```

## 4. Evaluation dimensions and rubric

Each applicable dimension receives `0` (poor/incorrect), `1` (partially
acceptable), or `2` (good). `N/A` is permitted when a dimension genuinely does
not apply.

| Dimension | Evaluation question |
| --- | --- |
| Relevance | Does the recommendation address the verified situation? |
| Actionability | Is the next tutor action concrete? |
| Evidence grounding | Are claims traceable to unchanged academic evidence? |
| Policy grounding | Is policy present, relevant and honestly qualified? |
| Explainability | Can the tutor understand why the action was selected? |
| Consistency | Do repeated/equivalent situations behave equivalently? |
| Context awareness | Do materially different situations receive distinct responses? |
| Data completeness | Is PARTIAL or unavailable information visible and honest? |
| Intervention quality | Are actions appropriate, ordered and non-duplicated? |
| Non-hallucination | Does output avoid unsupported facts and policies? |

A critical failure occurs if output invents facts or policy, contradicts
analytics, changes a risk classification, treats unavailable data as zero,
hides material PARTIAL status, gives an inappropriate high-impact action, or
provides no actionable response to clearly high risk.

## 5. Academic scenarios

1. Complete healthy/on-track assessment.
2. Moderate delay at the real 30 ECTS boundary.
3. Significant delay at the real 60 ECTS boundary.
4. Expiring study right as the primary concern.
5. Combined high progress delay and study-right concern.
6. Confirmed progress concern with tutor-meeting evidence unavailable.
7. One-ECTS deficit without meeting escalation.
8. Moderate delay with policy evidence.
9. Moderate delay with policy evidence unavailable.
10. Twenty-nine ECTS deficit immediately below the meeting threshold.

The scenarios use the current rules: any deficit is delayed; deficits below 30
are LOW, 30–59 are MEDIUM, and 60 or more are HIGH. Progress risk at MEDIUM or
higher adds a tutor-meeting recommendation. Study-right status drives its risk
factor without a numeric day threshold.

## 6. Results

All 21 objective evaluation checks passed. All ten scenarios met the critical
expectations. No hallucination, evidence-grounding, PARTIAL-data, consistency
or critical safety failure was observed.

| Scenario | Rel. | Act. | Evid. | Policy | Expl. | Cons. | Context | Data | Interv. | Non-hall. | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Healthy/on track | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 19/20 |
| Moderate delay | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 19/20 |
| Significant delay | 2 | 1 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 18/20 |
| Study-right concern | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 19/20 |
| Multiple factors | 2 | 2 | 1 | 1 | 1 | 2 | 2 | 2 | 2 | 2 | 17/20 |
| PARTIAL data | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 19/20 |
| One-ECTS deficit | 1 | 2 | 2 | 2 | 1 | 2 | 1 | 2 | 1 | 2 | 16/20 |
| Policy supported | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 19/20 |
| Policy unavailable | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 19/20 |
| 29 ECTS boundary | 2 | 2 | 2 | 2 | 1 | 2 | 1 | 2 | 1 | 2 | 17/20 |

Machine-readable scores and summary counts are in
`docs/evaluation/recommendation-quality-results.json`.

## 7. Strengths

- Recommendation types remain relevant to progress, study-right and deadline
  factors rather than collapsing into one generic response.
- Actions are deterministic and concrete: review a study plan, schedule a
  meeting, review study-right support, or continue monitoring.
- Student evidence preserves exact upstream ECTS and status values.
- Intervention types are deduplicated and consistently ordered.
- Healthy students do not receive meeting escalation.
- Policy failure produces a qualified fact-based action rather than fabricated
  university policy.
- PARTIAL status and unavailable dimensions are visible in rendered output;
  missing meeting information is not represented as zero meetings.
- Repeated and equivalent inputs produce identical decisions and rendering.

## 8. Weak recommendations

### W1 — Minimal deficits trigger intervention

- **Scenario:** One-ECTS deficit.
- **Observed:** The system recommends reviewing the study plan.
- **Why weak:** A one-credit difference may be administrative timing noise or
  too minor to justify tutor action.
- **Impact:** Low-to-medium risk of over-recommendation and tutor alert fatigue.
- **Likely component:** `risk_policy.py` and Recommendation Engine rules.
- **Suggested improvement:** Validate a tolerance band or persistence rule with
  academic stakeholders before changing the deterministic policy.

### W2 — Abrupt 29-to-30 ECTS escalation

- **Scenario:** Boundary comparison.
- **Observed:** 29 ECTS produces study-plan review only; 30 ECTS additionally
  schedules a tutor meeting.
- **Why weak:** The behavior is internally consistent but creates a sharp
  intervention discontinuity for a one-credit difference.
- **Impact:** Medium; near-equivalent students can receive materially different
  action sets.
- **Likely component:** Progress-risk and recommendation thresholds.
- **Suggested improvement:** Review threshold rationale and consider a confirmed
  trend, tolerance band or tutor-discretion qualifier.

### W3 — Repeated evidence and policy text

- **Scenario:** Moderate/high delay and multiple factors.
- **Observed:** Two recommendations derived from the same progress factor repeat
  identical evidence and the same policy excerpt.
- **Why weak:** The output is longer and harder to scan without adding evidence.
- **Impact:** Medium presentation-quality issue; grounding remains correct.
- **Likely component:** Recommendation template composition.
- **Suggested improvement:** Group actions by source factor and render shared
  evidence/policy once while preserving every intervention.

### W4 — Limited action personalization

- **Scenario:** Significant 60 ECTS delay.
- **Observed:** Actions remain “Review the student's study plan” and “Schedule a
  tutor meeting”; severity appears in evidence but not in the action wording.
- **Why weak:** The tutor knows what to do, but not what should be addressed in
  the review.
- **Impact:** Medium actionability limitation.
- **Likely component:** Recommendation action definitions.
- **Suggested improvement:** Safely parameterize action context from existing
  verified evidence without selecting new actions or inventing courses.

### W5 — Canonical risk explanation is absent from the main agent path

- **Scenario:** All LangGraph recommendation scenarios.
- **Observed:** Recommendation explanations preserve legacy risk-factor reasons,
  but #113 canonical score/factor explanations are not supplied automatically.
- **Why weak:** Tutors do not see canonical score provenance through this path.
- **Impact:** Medium explainability and architectural-consistency limitation.
- **Likely component:** Workflow integration between canonical risk scoring and
  the LangGraph Risk Agent.
- **Suggested improvement:** Define one authoritative risk contract and pass its
  existing #113 explanation to the recommendation state; do not recalculate it.

## 9. Improvement priorities

1. Review the one-ECTS and 29/30 ECTS escalation policy with academic owners.
2. Connect the existing #113 explanation contract to the tutor recommendation
   workflow through an agreed authoritative risk path.
3. Group repeated evidence and policy context in presentation output.
4. Add grounded severity context to existing action wording.
5. Add real tutor usability review before treating qualitative scores as final.

These are recommendations only; Issue #116 does not implement them.

## 10. Limitations

- Scenarios are synthetic and do not constitute a tutor-user study.
- Policy candidates are deterministic fixtures, not a full live-corpus RAG run.
- Qualitative scores reflect an explicit reviewer rubric but remain subjective.
- The agent and canonical risk-scoring paths are separate, so both are checked
  but not represented as one fully integrated end-to-end execution.
- The evaluation covers current supported recommendation types, not unsupported
  academic situations such as course-specific recovery planning.

## 11. Conclusion

The system meets the core Epic goals for deterministic, grounded and safe tutor
recommendations across the evaluated scenarios. It avoids critical grounding
and hallucination failures, handles missing policy and PARTIAL data honestly,
and distinguishes major academic concerns. Quality is not perfect: threshold
behavior can over-recommend near boundaries, multi-action templates repeat
content, high-risk actions could be more contextual, and canonical #113 risk
explanations are not yet connected to the main recommendation workflow.

## 12. Test results

- Evaluation tests: 21 passed.
- Recommendation, intervention, XAI and template regression: 83 passed.
- Agent and relevant analytics/risk regression: 361 passed, with one known
  CalendarAgent collaboration failure.
- Full backend suite: collection blocked by two existing `telegram.ext` import
  errors in notification-delivery and execution-logging tests.
- New regressions introduced by Issue #116: none. Issue #116 changes no
  production code.
