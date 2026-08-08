# Telegram Notifications (Issue #107)

## Scope

Issue #107 sends already-generated Issue #106 academic alerts to Tutor teachers
through Telegram. It owns recipient resolution, deterministic plain-text
rendering, Telegram provider delivery, and in-memory delivery results.

It does not calculate academic facts, create alerts, schedule jobs, register
Tutors, create tutor assignments, send to students, use group chats, add
preferences, retry messages, persist delivery history, or claim exactly-once
delivery.

## Automatic invocation

Issue #102 Daily Workflow is the automatic invocation owner. It already runs
through the Issue #100 scheduler and passes the exact
`AcademicAlertGenerationResult` from Issue #106 to the Issue #107 delivery
service. Issue #107 creates no second job or scheduler.

Issue #105 remains deferred. Its `WeeklyTutorBriefing` is a deterministic,
unsent text handoff, but no existing automatic workflow assembles it and its
final output has no Tutor identifier. Issue #107 does not alter #105 to invent
that orchestration.

## Authorized recipients

The approved limited-scope authority is an administrator-provisioned,
`is_active = TRUE` row in `tutors` with both `telegram_user_id` and
`telegram_chat_id` present. `TutorRepository.list_active_tutor_recipients_for_student()`
joins that Tutor with `tutor_student_assignments` and the affected Student.

Only Tutors assigned to the alert's student receive it. Multiple assigned Tutors
receive independently ordered messages. Missing, inactive, malformed, or
unmapped records are skipped with `NO_AUTHORIZED_TUTOR_RECIPIENT`; no fallback
recipient is selected.

The mapping is administrative provisioning, not runtime Telegram identity
registration. The application does not verify a new user, update the mapping,
support opt-out, or determine locale. The provisioning process must supply a
private Tutor chat; Issue #107 has no group-chat behavior.

## Alert templates

Templates are English, deterministic, and plain text:

- `academic_alert.delayed_progress.v1`
- `academic_alert.study_right_expired.v1`
- `academic_alert.study_right_expiring_soon.v1`
- `academic_alert.study_right_extended.v1`
- `academic_alert.overall_risk.v1`

They consume only established `AcademicAlert` fields. Student display names are
looked up only through the authorized Tutor-to-student assignment. Internal
student IDs, Telegram identifiers, email addresses, raw records, notes,
credentials, and full alert metadata are never rendered.

There is no Markdown or HTML parse mode. Dynamic display values are normalized
to one line, so no markup escaping contract is needed. The sender receives only
plain text. Messages longer than 4096 characters are split deterministically at
newlines or spaces when possible, then hard boundaries; every source character
is retained and parts are numbered in order.

## Delivery semantics

`TelegramApplicationSender` reuses the existing initialized
`python-telegram-bot` application. Scheduler worker-thread calls are marshalled
to the application event loop; no second Telegram client is created.

A delivery is `delivered` only after Telegram returns a message with a provider
message ID. This confirms Telegram API acceptance, not that a Tutor read the
message. The batch status is:

- `completed` when all eligible messages are delivered, or when a completed
  source contains no alerts;
- `partial` when an alert source is partial or some messages are skipped or
  fail while another result is usable;
- `failed` when the source fails or no delivery succeeds after an attempted
  batch.

Timeout/rate-limit, blocked-recipient, invalid-recipient/message, and generic
provider failures receive safe failure codes. No retry is attempted. Delivery
results, provider message IDs, and failure codes are in memory only; daily
workflow output and logs contain aggregate counts and safe codes only.

## Testing

Tests inject fake recipient resolvers and Telegram senders. They do not require
a token, a database, scheduler startup, network access, LLM, RAG, or Qdrant.
They cover deterministic recipient ordering, assignment scope, missing mappings,
template safety, chunking, provider acknowledgement, blocked recipients, source
availability, and the #102-to-#106-to-#107 handoff.
