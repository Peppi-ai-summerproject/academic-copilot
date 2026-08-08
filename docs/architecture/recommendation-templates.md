# Recommendation templates

Issue #115 provides a deterministic presentation layer for already-grounded
tutor recommendations. It controls structure, labels, optional sections and
availability notices. It does not calculate academic facts, classify risk,
select recommendations or interventions, or retrieve policy evidence.

## Architecture

```text
Analytics and risk
        |
RecommendationEngine (#110)
        |
RecommendationAgent (#111) -- InterventionSuggestionService (#112)
        |                     -- RiskExplanation (#113, when supplied)
        |                     -- ProgressExplanation (#114, when supplied)
        |                     -- retrieved policy evidence
        |
RecommendationTemplateService (#115)
        |
channel-independent rendered presentation
        |
CommunicationAgent / tutor-facing message
```

The template service is pure Python and has no LLM, RAG, MCP, database or
Telegram dependency. `CommunicationAgent` embeds its plain-text result in the
existing Telegram response. If a legacy recommendation result does not contain
a rendered presentation, the communication agent retains its previous action
formatting as a compatibility fallback.

## Supported scenarios

The default registry reflects the recommendation types currently produced by
the recommendation engine:

- `monitoring`: normal academic monitoring;
- `progress`: academic progress support;
- `study_right`: study-right support;
- `deadline`: academic deadline support.

Unknown upstream types use a neutral tutor-recommendation label. This fallback
only presents the supplied action; it does not define new recommendation rules.

## Structure and optional sections

Every output begins with a recommendation section. For each upstream decision,
the renderer preserves its priority, explanation and action. It then composes
available sections in this stable order:

1. supporting student evidence;
2. suggested interventions, in upstream order;
3. risk explanation;
4. progress explanation;
5. relevant policy guidance;
6. data-availability information.

Absent optional values produce no empty headings. Evidence values and policy
excerpts are copied from upstream structures. Interventions are neither
selected nor reordered. The renderer does not query RAG; it only presents the
policy candidates already attached by `RecommendationAgent`.

## Explanations and incomplete data

The risk and progress explanation sections consume the structured summaries
and warnings produced by Issues #113 and #114. They are optional because the
corresponding upstream workflow may not have supplied them. Their absence is
never reconstructed from raw risk factors or ECTS values.

When `data_status` is `PARTIAL`, the rendered output displays that status plus
the existing `missing_information` and `unavailable_dimensions`. Missing facts
are not converted to zero, `none`, a healthy state, or any other conclusion.

## Adding a scenario

Create a small `ScenarioTemplate` and provide it when constructing the service:

```python
service = RecommendationTemplateService({
    "new_upstream_type": ScenarioTemplate(
        title="New support scenario",
        situation_label="Verified situation",
    ),
})
```

Then add focused rendering tests. No analytics, risk policy, intervention
mapping, agent route or channel-delivery code needs to change. The same input
always produces the same output.
