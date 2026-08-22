# Demo Scenario 1 — Student Academic Progress Overview

## Goal

Demonstrate that a tutor can use Telegram to identify a student, retrieve
canonical academic facts, evaluate progress and risk, inspect failed results,
receive an evidence-based advisory action, and continue the conversation using
the resolved student context.

## Persona

The user is a tutor teacher reviewing a student's academic situation before a
tutor meeting.

## Student

Use **Matias Multiple** (`DEMO25204`) from student group **DIN24** in the
Business IT programme. Matias is a useful deterministic persona because his
record combines one passed course with two failed courses and a substantial
credit deficit. No application behavior is specific to Matias.

## Preconditions

- The backend is healthy and connected to the intended academic database.
- Migrations through `010_seed_realistic_academic_demo_dataset.sql` have been
  applied to the demo environment.
- The Telegram webhook is configured for that backend.
- Matias (`DEMO25204`) and the DIN24 course/result records below exist.
- Start in a new Telegram chat or clear/know the current conversation context.

## Demo Script

### 1. Resolve the student

- **Tutor message:** `Show me Matias Multiple.`
- **Expected path:** student lookup → Academic Entity Resolution → tutor academic
  data query → gateway/MCP student lookup.
- **Important response content:** `Matias Multiple` and `DEMO25204`.
- **Demonstrates:** a human-readable name is resolved to the canonical student;
  the resolved STUDENT becomes active conversation context.

### 2. Review progress

- **Tutor message:** `How is he progressing?`
- **Expected path:** progress workflow using the active STUDENT context.
- **Important response content:** Matias, 5 completed ECTS, 30 expected ECTS,
  25 ECTS behind, semester 1, and BEHIND/16.7% progress wording.
- **Demonstrates:** pronoun context reuse and authoritative progress calculation.

### 3. Inspect the first failed result

- **Tutor message:** `Did he pass DBS24?`
- **Expected path:** student-course result query through the academic gateway.
- **Important response content:** Matias, `FAILED`, and `grade 0`. The course is
  explicit in the tutor's question; the current result renderer does not repeat
  its code in this single-course reply.
- **Demonstrates:** a student-specific yes/no question returns the actual result;
  grade zero is preserved rather than treated as missing.

### 4. Confirm the second failed result

- **Tutor message:** `Did he pass WEB24?`
- **Expected path:** student-course result query, retaining the same STUDENT and
  replacing only the active COURSE context.
- **Important response content:** Matias, `FAILED`, and `grade 0`. As above, the
  current renderer does not repeat the course code.
- **Demonstrates:** repeated contextual exploration across canonical courses.

### 5. Evaluate academic risk

- **Tutor message:** `Is he at risk?`
- **Expected path:** progress and study-right dependencies → deterministic risk
  agent → tutor-facing response.
- **Important response content:** Matias has LOW academic risk because his 5 ECTS
  are below the expected 30 ECTS.
- **Demonstrates:** risk is derived from verified academic dimensions, not from
  the presence of a failed grade alone.

### 6. Ask for a tutor action

- **Tutor message:** `What academic next steps do you recommend for this student?`
- **Expected path:** progress and study-right dependencies → risk → recommendation
  engine and optional policy retrieval → tutor-facing recommendation template.
- **Important response content:** an advisory action to review the student's
  study plan. The response includes an availability note if policy evidence or
  another optional dimension is unavailable.
- **Demonstrates:** recommendations are grounded in the current student's
  calculated risk evidence and remain advisory.

## Expected Academic State

| Fact | Deterministic value |
|---|---|
| Student number | DEMO25204 |
| Student | Matias Multiple |
| Student group | DIN24 |
| Programme | Business IT |
| Enrollments | All configured DIN24 courses |
| DII101 | PASSED, grade 2, 5 ECTS |
| DBS24 | FAILED, grade 0, 0 earned ECTS |
| WEB24 | FAILED, grade 0, 0 earned ECTS |
| Other configured courses | Enrollment without completion |
| Completed credits | 5 ECTS |
| Expected credits | 30 ECTS at semester 1 |
| Difference | 25 ECTS behind |
| Progress | BEHIND, 16.7% of expected progress |
| Deterministic progress risk | LOW |

FAILED completions contribute zero credits. Enrollments without completions do
not become passed results. The current risk policy scores Matias's progress
deficit; it does not infer additional risk merely from counting failed courses.

## Architecture Path

`Telegram handler → backend chat API/client → ChatService → intent and dependency routing → AcademicEntityResolver/conversation context → specialized agent workflow → AcademicToolGateway → MCP tool → academic service/repository → PostgreSQL/Supabase`

Progress, risk, and recommendation calculations remain in their existing
services/agents. The demo does not query the database from ChatService or an
agent and does not contain persona-specific production behavior.

## Presentation Notes

- After step 1, point out that the displayed student number is the canonical
  identity used by later calls.
- At step 2, emphasize that the tutor did not repeat Matias's name.
- At steps 3–4, call out both the FAILED status and grade 0.
- At step 5, explain that the risk statement is calculated from verified data.
- At step 6, distinguish advisory tutor support from automated decision-making.

## Failure / Recovery Notes

- If lookup is ambiguous, retry with `Show me DEMO25204.`
- If the student or results are missing, verify migration 010 was applied to the
  selected demo database; do not add records through Telegram or agent code.
- If a pronoun asks for clarification, restart with the explicit lookup and keep
  subsequent messages in the same Telegram chat.
- If recommendations show an availability note, verify policy/RAG configuration.
  The deterministic study-plan action can still be produced from verified risk
  evidence, but unavailable policy evidence must not be presented as verified.

## Pre-demo Checklist

- Backend health check succeeds.
- Telegram webhook points to the intended backend.
- Migration 010 is recorded as applied in the demo environment.
- `DEMO25204`, DBS24, DII101, and WEB24 records match the table above.
- Progress and academic MCP tools respond successfully.
- Recommendation policy retrieval is available, or its controlled partial-state
  behavior has been rehearsed.
- The Telegram conversation begins with a clean or known context.
