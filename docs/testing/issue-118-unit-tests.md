# Issue #118 Unit-Test Audit

## Scope

Issue #118 audited isolated backend coverage and added focused tests for
meaningful gaps. It did not introduce a new test framework, change production
behavior, or duplicate the extensive existing analytics suites.

The audit inspected `backend/app`, `backend/tests`, `pytest.ini`, backend
requirements, configuration, services, analytics, utilities, repositories,
MCP helpers, agent helpers and existing testing documentation.

## Existing coverage

The repository already has substantial isolated coverage for:

- ECTS analytics and combined progress calculations;
- expected curriculum progress and delay detection;
- study-right and tutor-meeting risk;
- canonical academic risk scoring and all score boundaries;
- academic health scoring, including inverse risk conversion and overrides;
- recommendation, intervention and explanation services;
- configuration defaults and selected environment overrides;
- repositories and service error propagation;
- state reducers, session memory and deterministic formatting helpers.

Those tests remain the authoritative coverage and were not recreated.

## Gaps addressed

### Pure risk-policy helpers

`backend/tests/services/test_risk_policy.py` directly tests the isolated legacy
agent policy helpers that were previously covered only through agent tests:

- LOW/MEDIUM/HIGH ECTS deficit boundaries;
- completed/expected fallback when signed difference is unavailable;
- non-behind and safe study-right behavior;
- study-right date serialization and extension preservation;
- inclusive 0–14 day deadline window and exclusion of past/future events;
- `datetime` normalization;
- malformed-event disclosure while retaining valid events;
- non-global/non-deadline filtering;
- stable highest-risk selection and defaults.

### Configuration validation

`backend/tests/test_config.py` now also covers:

- the successful enabled-webhook configuration path with test-only credentials;
- accepted false boolean environment values without credentials;
- rejection of hours/minutes outside valid clock bounds.

Tests never load or expose developer secrets and do not depend on the real
`.env` file.

### Academic-health service boundaries

`backend/tests/services/test_academic_health_score_service.py` now verifies
that invalid student IDs and invalid reference dates are rejected before the
canonical risk dependency is called.

## Verification

Commands used from the repository root used Python 3.11 with `DEBUG=false` and
the existing temporary dependency path.

Focused changed modules:

```text
70 passed
```

Affected configuration and analytics suites:

```text
329 passed
```

Full backend collection initially remains blocked by two pre-existing missing
`telegram.ext` imports in notification-delivery and execution-logging tests.
Running the remaining backend suite produced:

| Run | Passed | Failed | Warnings |
| --- | ---: | ---: | ---: |
| Before Issue #118 changes | 815 | 28 | 1 |
| After Issue #118 changes | 849 | 28 | 1 |

The 34 additional cases all pass. The same baseline failures remain:

- CalendarAgent constructor mismatch in one collaboration test;
- stale MCP integration assumptions about tool count and removed
  module-level `SessionLocal` attributes;
- workflow lifecycle tests affected by the unavailable Telegram package in
  this temporary environment.

No new regression was introduced.

## Acceptance criteria

- [x] Unit tests created — 34 additional isolated cases.
- [x] Key backend functions covered — risk-policy and configuration helpers.
- [x] Analytics functions tested — risk boundaries, deadline calculations and
  academic-health validation.
- [x] Tests run successfully locally — all new and affected tests pass.

## Deferred scope

The following were intentionally not expanded:

- #119: cross-service and API integration tests;
- #120: MCP registration, transport and tool integration tests;
- #121: agent orchestration and collaboration tests;
- #122: RAG retrieval and generation tests;
- #123: load and performance testing;
- #124: security and authorization testing;
- #125: full end-to-end workflows with external infrastructure.

Production files modified: none.
