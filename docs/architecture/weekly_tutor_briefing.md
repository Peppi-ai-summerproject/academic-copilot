# Weekly Tutor Briefing (Issue #105)

## Ownership and boundaries

Issue #105 creates a deterministic, per-tutor briefing for the **previous
completed week**. It is intentionally separate from Issue #101, which keeps
its existing upcoming-week Monday preparation briefing unchanged.

`WeeklyTutorBriefingGenerator.generate()` accepts a caller-assembled
`WeeklyTutorBriefingInput`. It does not start a scheduler, open a database
session, calculate progress or risk, persist a report, call an LLM/RAG service,
or send a Telegram message.

- Issue #103 owns the completed-week reporting period and aggregate workflow.
- Issue #104 owns canonical active-student risk detection.
- Issue #105 owns composition of a tutor-scoped, presentation-safe briefing.
- Issue #107 remains the owner of Telegram delivery, destinations, message-size
  policy, and chunking.

## Input and recommendation boundary

The input is deliberately tutor-scoped: it carries one real tutor audience,
the number of assigned students, and only students already selected as requiring
tutor attention. Each included student must have a matching canonical
`StudentRiskDetectionResult` from #104. Current progress is optional and is
explicitly a current-state snapshot, not a claim about ECTS completed during
the week.

`OfflineRecommendationAdapter` maps only the non-zero
`StudentRiskDetectionResult.actionable_indicators` to the existing advisory
wording:

- `academic_delay`: review the study plan; for a canonical attention result,
  schedule a tutor meeting;
- `study_right`: check extension/support options;
- `academic_events`: review the deadline and agree a next step.

The adapter never performs policy retrieval, RAG, LLM calls, or network I/O.
Unknown or absent actionable indicators produce an availability note instead
of an invented action.

## Output, privacy, and Telegram handoff

`WeeklyTutorBriefing` is a serializable structured output accompanied by a
plain-text `TelegramReadyBriefing` with `delivery_status = NOT_SENT`. It has no
Telegram chat ID, token, ORM entity, stable student ID, student number, email,
meeting notes, or study notes. Dynamic display values are normalised to one
line before they are rendered. Plain text preserves Unicode; there is no
Markdown/HTML parse mode or escape contract in the existing delivery code.

Risk severity order is `CRITICAL`, `HIGH`, then `MEDIUM`, followed by student
display name. A partial source, partial risk assessment, missing progress, or
unmapped recommendation evidence remains explicit and is never shown as low
risk. Telegram size enforcement and splitting are intentionally deferred to
Issue #107 because the repository has no established maximum-size/chunking
contract.

## Testing

Focused tests are pure and require no FastAPI, scheduler, database, Telegram,
LLM, RAG, Qdrant, or network access:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\workflows\test_weekly_tutor_briefing.py backend\tests\workflows\test_automatic_risk_detection.py
```
