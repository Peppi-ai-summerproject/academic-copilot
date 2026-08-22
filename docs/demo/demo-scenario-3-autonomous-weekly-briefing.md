# Demo Scenario 3 — Autonomous Weekly Tutor Briefing

## Goal

Demonstrate proactive behavior: the scheduler runs the production Monday tutor
workflow, analyses each tutor's assigned students, generates a weekly briefing,
sends it through the configured Telegram application, and records aggregate
execution history without waiting for a tutor question.

## Workflow Selected

Scenario 3 uses `MondayWorkflow`, registered as scheduler job
`monday_workflow`. This is the only existing production workflow that creates a
tutor-scoped, Telegram-ready briefing. The separately named `WeeklyWorkflow`
creates and stores aggregate previous-week reports but explicitly does not own
tutor-specific briefing text or delivery. `DailyWorkflow` sends individual
academic alerts rather than a weekly tutor briefing.

## Preconditions

- The deployed backend is healthy and can reach PostgreSQL/Supabase.
- Required migrations, including tutor assignments and workflow execution logs,
  are already applied. Do not run migrations as part of the presentation.
- The realistic DIN24 dataset is present.
- At least one active `tutors` row has non-null `telegram_user_id` and
  `telegram_chat_id` values provisioned administratively.
- `tutor_student_assignments` associates that tutor with the intended students.
- The assigned students have sufficient curriculum, progress, and risk evidence.
  Missing dimensions remain visible as availability warnings.
- `TELEGRAM_BOT_TOKEN` is configured. For normal scheduled operation,
  `TELEGRAM_WEBHOOK_ENABLED=true` initializes the lifecycle-owned sender.
- `SCHEDULER_ENABLED=true`; `SCHEDULER_TIMEZONE`, `MONDAY_WORKFLOW_HOUR`, and
  `MONDAY_WORKFLOW_MINUTE` are configured for the deployment.

Never display environment values, bot tokens, webhook secrets, database URLs,
Telegram identifiers, or other credentials during the presentation.

## Normal Production Trigger

During FastAPI lifespan startup, `app.main.lifespan` starts the existing
`Scheduler` when `SCHEDULER_ENABLED=true`. `register_monday_workflow` registers
`run_scheduled_monday_workflow` for Monday (`weekday=0`) at the configured hour
and minute in `SCHEDULER_TIMEZONE`.

The scheduled entry point calls the database-backed runner with
`trigger_type="scheduler"`. It uses the same workflow, delivery, and logging
code as the manual presentation trigger.

## Safe Presentation Trigger

From the `backend` directory, after verifying the target environment and tutor
recipient, run:

```powershell
..\.venv\Scripts\python.exe scripts\run_monday_briefing.py --confirm-send
```

The required flag prevents an accidental send. The command initializes the
existing Telegram application, invokes `run_manual_monday_workflow` in its
worker thread, and shuts the application down cleanly. It is a server-side CLI,
not a public HTTP endpoint. It executes the same database runner used by the
scheduler, with only the execution-log trigger type changing from `scheduler`
to `direct`.

This command sends real messages to every eligible active tutor returned by the
production workflow. Use it only after checking the database and environment.

## Execution Flow

`FastAPI lifespan → Scheduler → run_scheduled_monday_workflow → run_database_monday_workflow → MondayWorkflow → TutorRepository assignments + ProgressService + AcademicRiskScoringService + EventService → Monday briefing renderer → AutonomousMondayBriefingRunner → configured TelegramApplicationSender → Telegram Bot API → WorkflowExecutionRecorder → WorkflowExecutionLogRepository`

`MondayWorkflow` reaches academic data through the existing service/repository
boundaries. It composes already-calculated progress and risk results; it does
not duplicate those calculations. AcademicToolGateway/MCP and interactive
agents are not on this autonomous path and are therefore not claimed here.

## Briefing Contract

Each `MondayTutorBriefing` contains:

- Tutor ID/name and the Monday-to-Sunday reporting window
- Assigned and successfully analysed student counts
- Students with verified non-zero risk-indicator contributions
- Progress and risk payloads for those priority students
- Upcoming academic events for the week
- Explicit availability warnings
- Deterministically rendered Telegram text and delivery status

The Telegram presentation includes the tutor name, week, assigned count,
attention count, priority student names, ECTS below expected when available,
upcoming items, and availability notes. It intentionally does not expose raw
risk payloads, Telegram IDs, or secrets.

The Monday workflow's `students_needing_attention` is an operational attention
signal: at least one verified canonical indicator contributed non-zero points.
It must not be described as the Issue #104 MEDIUM/HIGH/CRITICAL attention list.
Incomplete evidence remains PARTIAL/UNAVAILABLE and is never treated as safe.

## Expected Demonstration Briefing

Exact names and counts depend on current tutor assignments and evidence. With a
demo tutor assigned to the relevant DIN24 students, representative deterministic
content includes:

- `Monday briefing for <configured tutor>`
- The current Monday-to-Sunday week
- The configured assigned-student count
- Students with verified progress/risk contributions
- An ECTS deficit such as `Oskari Example; 30 ECTS below expected`, when the
  current canonical data produces that progress result
- Current-week events, if any
- Availability notes for missing study-right, meeting, event, or progress data

Course completions and progress are deterministic academic facts. The week
window and upcoming events are date-dependent. Overall risk may be partial or
unprocessable when required evidence is absent; the message must retain that
qualification.

## Expected Telegram Notification

The tutor receives the exact `delivery.text` generated inside
`MondayWorkflow`. `AutonomousMondayBriefingRunner` sends that text unchanged to
the tutor record's `telegram_chat_id` through the lifecycle-configured
`TelegramApplicationSender`.

Successful acknowledgement changes the briefing status from `NOT_SENT` to
`DELIVERED` and records the provider message ID in the in-memory result. Missing
destinations remain `NO_DESTINATION`; an unavailable sender becomes
`UNAVAILABLE`; transport exceptions become `FAILED` and make an otherwise
completed run partial.

## Tutor and Recipient Resolution

`TutorRepository.list_active_tutors()` selects active tutor records and their
administratively provisioned Telegram identifiers. For each tutor,
`list_students_for_tutor(tutor_id)` follows `tutor_student_assignments` to define
the academic scope. The workflow never hardcodes a tutor, student, or chat ID.

## Workflow Logging

`WorkflowExecutionRecorder` writes aggregate-only lifecycle metadata through
`WorkflowExecutionLogRepository`:

- Workflow name `monday_tutor_briefing`
- Trigger type (`scheduler` or `direct`)
- Running and final timestamps/duration
- Requested/processed briefing counts
- Delivered, failed, and skipped counts
- Warning/error counts and safe codes

Rendered messages, tutor names, student names, Telegram IDs, and academic
payloads are not persisted in workflow history. Application logs also emit the
final status, week start, and briefing count.

## Presentation Script

1. Open the tutor's Telegram conversation and show that no tutor query initiated
   the scenario.
2. Show the configured Monday scheduler job without revealing secrets.
3. Confirm the active tutor assignment and Telegram mapping through an approved
   administrative view.
4. Run the confirmation-gated command above.
5. Show the command's aggregate status and the backend workflow log entry.
6. Return to Telegram and open the automatically delivered Monday briefing.
7. Explain the assigned count, attention signal, verified ECTS evidence, events,
   and any availability qualifications.
8. Optionally continue with `Show me <student name>.` through the separate
   interactive ChatService path; clarify that this follow-up is not part of the
   autonomous workflow execution.

## Technical Talking Points

- FastAPI lifecycle and in-process timezone-aware scheduler
- Production Monday workflow orchestration
- Tutor and student assignment repositories
- Progress, risk, study-right, meeting, and event services
- Deterministic briefing rendering
- Shared Telegram application transport
- Aggregate, privacy-safe workflow execution logging
- Controlled PARTIAL/UNAVAILABLE behavior
- Separation between autonomous workflows and interactive agent/MCP paths

## Failure / Recovery Notes

- **No message:** verify the tutor is active and has both Telegram identifiers;
  check `tutor_student_assignments` and the briefing delivery status.
- **Sender unavailable:** ensure the Telegram application initialized before the
  scheduler and that webhook integration is enabled in normal production.
- **Telegram failure:** inspect safe application logs and connectivity; do not
  print or rotate secrets on the presentation screen.
- **Database failure:** verify backend database connectivity and migration state.
- **Partial briefing:** inspect the named unavailable academic dimensions. Do not
  claim that an omitted student is safe.
- **No upcoming events:** events are week- and date-sensitive; an empty section
  is valid.
- **Duplicate notifications:** the current Monday delivery has no durable
  per-recipient deduplication key. Do not run the manual command repeatedly.
  Workflow logs provide an audit trail but do not suppress a second send.
- **Scheduler disabled:** use the manual command only after validating its target;
  re-enable normal scheduling through deployment configuration.

## Pre-presentation Checklist

- Main branch is deployed and backend health succeeds.
- PostgreSQL/Supabase is reachable.
- Required migrations and DIN24 data are verified.
- Tutor is active, assigned to the intended students, and has a private Telegram
  user/chat mapping.
- Telegram bot and webhook lifecycle are healthy.
- Scheduler timezone and Monday schedule are correct.
- Progress/risk availability for assigned students has been reviewed.
- Manual trigger command and `--confirm-send` behavior were rehearsed in a safe
  environment.
- Expected briefing wording and current-week events were checked.
- Workflow and application logs are accessible.
- The command will be run only once.
- No secrets or real identifiers are visible on screen.

## Post-deployment Verification

1. Confirm the migration history and required tutor/assignment rows through the
   approved administrative database tooling.
2. Confirm Telegram webhook initialization and scheduler job-registration logs.
3. Verify the tutor has initiated or otherwise authorized the private bot chat
   and that the stored mapping is correct.
4. Review current academic evidence and expected briefing before sending.
5. Run the manual command once with `--confirm-send`.
6. Confirm its aggregate `status`, `execution_key`, and briefing count.
7. Inspect the latest `monday_tutor_briefing` execution log for the `direct`
   trigger and delivered/failed/skipped counts.
8. Confirm Telegram received the same meaningful briefing text.
9. If successful, leave normal scheduler configuration enabled for the next
   Monday run; do not repeat the manual send.
