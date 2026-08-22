# Demo Scenario 2 — Academic Risk Detection and Explanation

## Goal

Demonstrate a tutor moving from a cohort-level academic concern to a canonical
student risk explanation and evidence-based recommended action. This differs
from Scenario 1: the tutor does not begin with a known student.

## Tutor Persona

A tutor teacher reviews DIN24 for students whose verified course results merit
attention, selects one student, and asks the system to assess and explain that
student's academic risk.

## Preconditions

- The backend and Telegram webhook are healthy.
- Migrations through `010_seed_realistic_academic_demo_dataset.sql` are applied
  to the demo environment.
- DIN24 group membership and DBS24 completions match the dataset below.
- Oskari's progress, study-right, and event tools are available. The scripted
  individual risk result assumes the canonical demo state described below.
- Recommendation policy retrieval is configured, or its controlled PARTIAL
  behavior has been rehearsed.
- Begin with a clean or known Telegram conversation context.

## Dataset / Students Used

The first query uses authoritative DBS24 results for DIN24:

| Student | DBS24 result | Included in FAILED view |
|---|---|---|
| Elina Demo | PASSED, grade 4 | No |
| Oskari Example | FAILED, grade 0 | Yes |
| Sofia Sample | No completion | No |
| Aava Achiever | PASSED, grade 5 | No |
| Petra Partial | FAILED, grade 0 | Yes |
| Matias Multiple | FAILED, grade 0 | Yes |
| Eero Mixed | PASSED, grade 4 | No |

Oskari Example (`DEMO22102`, canonical student ID resolved at runtime) is then
selected because the seeded passed-credit record gives him 0 completed ECTS
against 30 expected in semester 1. This is a data-backed reason to assess him;
a failed result alone is not declared to be an overall risk classification.

## Risk Model Semantics

- **Progress** compares passed ECTS with the curriculum expectation. Oskari is
  BEHIND: 0 completed, 30 expected, a 30 ECTS deficit.
- **Individual agent risk** maps verified dimensions independently and reports
  the highest factor. A 30–59 ECTS progress deficit is MEDIUM under the current
  agent risk policy.
- **Canonical overall risk scoring** is a separate Issue #95 model combining
  academic delay, study right, tutor meetings, and academic events into 0–100.
  MEDIUM/HIGH/CRITICAL results require tutor attention; LOW does not.
- **Academic health** reverses a complete canonical overall score
  (`health_score = 100 - risk_score`). It is not another risk calculation and
  is not claimed by this Telegram script.
- **Attention candidate** in step 2 means a student with a verified FAILED
  course result who merits tutor review. It does not mean the automatic
  workflow has already assigned that student a canonical overall risk level.

This distinction explains why Matias in Scenario 1 can be BEHIND yet have LOW
individual progress risk: his 25 ECTS deficit is below the 30 ECTS MEDIUM
boundary. Oskari's 30 ECTS deficit is exactly the inclusive MEDIUM boundary.

## Demo Script

### 1. Establish the cohort

- **Tutor message:** `Show me DIN24.`
- **Expected response:** canonical DIN24 student-group details.
- **Evidence:** resolved STUDENT_GROUP context.
- **Demonstrates:** cohort resolution without treating DIN24 as a course.

### 2. Identify students requiring result review

- **Tutor message:** `Who failed Database Systems in DIN24?`
- **Expected response:** Oskari Example, Petra Partial, and Matias Multiple;
  each is FAILED with grade 0. Elina, Aava, Eero, and Sofia are excluded.
- **Evidence:** canonical DBS24 completions filtered to FAILED and scoped by
  canonical DIN24 membership.
- **Demonstrates:** production cohort discovery through ChatService,
  AcademicEntityResolver, AcademicToolGateway, MCP/service/repository, and the
  existing group-course-results capability. This is an attention-candidate
  list, not a fabricated cohort-wide risk score.

### 3. Select one student

- **Tutor message:** `Show me Oskari Example.`
- **Expected response:** Oskari Example and `DEMO22102`.
- **Evidence:** canonical STUDENT resolution.
- **Demonstrates:** the selected STUDENT is added while unrelated DIN24 context
  remains valid.

### 4. Explain the detected risk

- **Tutor message:** `Why is he at risk?`
- **Expected response:** Oskari has MEDIUM academic risk because he is 30 ECTS
  behind expected progress.
- **Evidence:** 0 completed ECTS, 30 expected ECTS, 30 ECTS deficit, BEHIND.
- **Demonstrates:** pronoun context reuse and fact-based explanation. No failed
  course count is invented as a risk input.

### 5. Generate tutor actions

- **Tutor message:** `What academic next steps do you recommend for this student?`
- **Expected response:** MEDIUM-priority advisory actions to review the study
  plan and schedule a tutor meeting, supported by the verified progress deficit.
  Availability qualifications remain visible if optional policy evidence is
  unavailable.
- **Evidence:** RecommendationAgent consumes the preceding workflow's structured
  risk factor and uses the existing engine/template mappings.
- **Demonstrates:** recommendation content reaches Telegram through ChatService;
  no response is hardcoded for Oskari.

## Expected Risk State

| Value | Expected result |
|---|---|
| Student | Oskari Example / DEMO22102 |
| Completed credits | 0 ECTS |
| Expected credits | 30 ECTS |
| Progress difference | −30 ECTS |
| Progress status | BEHIND |
| Individual progress risk | MEDIUM |
| Evidence | Student is 30 ECTS behind expected progress |
| Recommended priority | MEDIUM |
| Recommended actions | Review study plan; schedule tutor meeting |

The Telegram risk agent result above is not presented as an Issue #95 overall
risk score or academic-health score.

## Why the Student Was Flagged

1. The cohort query proves a DBS24 FAILED completion with grade 0. This makes
   Oskari a review candidate but does not itself set his risk level.
2. The risk agent retrieves canonical progress and verifies the 30 ECTS deficit.
3. The current agent risk policy maps that deficit to MEDIUM.
4. Recommendation rules consume that structured progress-risk evidence.

## Recommendation

The expected advisory behavior comes from RecommendationAgent,
RecommendationEngine, and RecommendationTemplateService. It should expose
MEDIUM priority, the evidence behind the decision, study-plan review, and a
tutor meeting. Policy/RAG evidence may enrich the response but must never be
fabricated; missing evidence produces a PARTIAL/availability qualification.

## Automatic Identification Capability and Gap

`AutomaticRiskDetectionWorkflow` already scans ACTIVE students through
StudentRepository and AcademicRiskScoringService. It evaluates the canonical
Issue #95 model, retains only MEDIUM/HIGH/CRITICAL results, sorts by severity,
and feeds daily alerts and weekly tutor briefings.

However, two constraints prevent the final Telegram script from truthfully
starting with `Which students in DIN24 need academic attention?`:

1. There is no current tutor intent, AcademicToolGateway/MCP operation, or
   group-scoped service contract exposing the automatic attention list to an
   interactive Telegram query.
2. Migration 010 seeds progress/results but not deterministic study-right,
   tutor-meeting, or date-stable academic-event evidence. Therefore it does not
   guarantee reproducible complete Issue #95 scores for these personas.

The demo consequently uses the supported FAILED-result cohort view for initial
discovery and clearly labels it as candidate selection. Adding an interactive
cohort-risk API/tool and a separately reviewed deterministic risk-evidence
dataset is future work; neither is hidden inside this demo implementation.

## Architecture Path

Interactive path:

`Telegram handler → backend client/API → ChatService → intent/dependency routing → AcademicEntityResolver and conversation context → agent workflow → AcademicToolGateway → MCP → academic service/repository → PostgreSQL/Supabase → risk/recommendation explanation → Telegram`

Automatic path already implemented outside this script:

`Daily scheduler/workflow → AutomaticRiskDetectionWorkflow → StudentRepository → AcademicRiskScoringService → delay/study-right/meeting/event services and repositories → AcademicAlertWorkflow / WeeklyTutorBriefing → Telegram notification delivery`

## Presentation Notes

- Explicitly call step 2 a result-based attention shortlist, not an overall
  risk ranking.
- Point out the transition from cohort context to canonical student context.
- At step 4, show the 30 ECTS fact before discussing MEDIUM interpretation.
- At step 5, distinguish verified facts from advisory actions.
- Mention that the automatic batch workflow exists, while interactive
  group-scoped risk discovery is a known exposure gap.

## Failure / Recovery Notes

- If Database Systems is globally ambiguous, begin with `Show me DIN24.` so
  group membership narrows it to DBS24.
- If Oskari is ambiguous, use `Show me DEMO22102.`
- If risk is PARTIAL or inconclusive, inspect progress, study-right, and event
  tool availability; never interpret missing evidence as safe.
- If the expected risk level differs, verify Oskari's passed-credit total and
  curriculum expectation rather than altering a result for presentation.
- If recommendations lack policy enrichment, confirm RAG configuration and
  retain the displayed availability qualification.
- If Telegram fails, verify webhook/backend connectivity and keep every turn in
  the same chat.

## Pre-demo Checklist

- Backend health check passes.
- Telegram webhook targets the intended backend.
- Migrations through 010 are applied.
- DIN24, DBS24, and Oskari's canonical records match this document.
- Progress, study-right, event, and academic MCP tools respond.
- Recommendation/RAG availability behavior has been rehearsed.
- Conversation context is clean or known.
- The scheduled workflow is enabled only if its separate automatic path will be
  discussed or demonstrated.
