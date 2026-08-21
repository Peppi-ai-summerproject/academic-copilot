# Issue #245 — Student-group academic workflow validation

## Corrected domain model

DIN24 is a `STUDENT_GROUP`, not a course. DII101 is the independent course
Digital Innovation Foundations. Groups contain students and are associated with
courses; teacher assignments belong to courses.

## Automated scenarios

The production-style E2E suite validates group lookup, group students, group
courses (DII101, DBS24, and WEB24), course-teacher composition, invalid
group/course relationships, student result and grade follow-ups, group-scoped
passed/failed results, context switching, failed/ambiguous switch preservation,
and Telegram multi-turn delivery. Assertions cover canonical IDs and entity
types as well as meaningful names, codes, statuses, grades, and exclusions.

The suite uses the real `ChatService`, deterministic intent detection, academic
entity resolver, conversation memory, workflow, and tutor agents. Only the
database/MCP transport boundary is replaced by a deterministic academic gateway.

## Manual Telegram verification

Use a non-production test environment with Issue #243 data and verify:

1. `Show me DIN24.`
2. `Which students are in it?`
3. `Which courses does it have?`
4. `Who teaches Database Systems?`
5. `Show me Elina Demo.`
6. `Did she pass DII101?`
7. `What grade did she get?`

Expected results identify DIN24 as a group, list its canonical students and
courses, return the course's teacher, and report Elina's stored status and grade.
