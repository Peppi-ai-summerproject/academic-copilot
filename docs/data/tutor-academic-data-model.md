# Tutor academic data model (Issue #221)

## Audit

The backend has no SQLAlchemy domain models; repositories intentionally execute
parameterized SQL through SQLAlchemy sessions. The original simulated Peppi base
schema is deployed outside this repository, while later additive PostgreSQL
migrations are versioned in `backend/db/migrations`.

| Capability | Status before #221 | Authoritative structure and gap |
| --- | --- | --- |
| Student internal ID | Existing | `students.id` |
| Academic student identifier | Existing | `students.student_number`; search already supports it |
| Student name/programme/group/status | Existing | `students` and `StudentRepository` |
| Student contact | Missing | no email selected or documented |
| Programme progress | Existing | `course_completions` credits plus `curriculum` milestones |
| Individual course | Missing | curriculum is a milestone table, not a course catalog |
| Enrollment | Missing | no student–course relationship |
| Course result | Partial | `course_completions` is the existing credit source, but had no course FK or pass/fail contract |
| Tutor/teacher | Partial | `tutors` supports Telegram delivery and tutor–student assignment; no email/course relation |
| Teacher–course assignment | Missing | no relation existed |

Study rights, events, tutor meetings, risk events/workflows, MCP tools and agents
were audited but do not replace course/enrollment/result concepts.

## Minimal extension

The implementation reuses the three authoritative records rather than creating
parallel Student, Teacher or Result concepts:

- `students`: adds optional unique case-insensitive email;
- `tutors`: remains the staff/tutor-teacher record and adds optional unique
  case-insensitive email;
- `course_completions`: remains the progress/result source and adds nullable
  `course_id`, `result_status`, `grade`, and `completion_date`;
- `courses`: searchable teaching-unit catalog with stable `course_code`;
- `course_enrollments`: unique student–course membership and current enrollment
  state;
- `teacher_course_assignments`: many-to-many tutor/teacher–course relation with
  assignment role.

Existing completion rows migrate to `result_status='PASSED'`. Progress explicitly
sums only passed rows and treats a legacy null status as passed. Failed records
may retain the course credit value but never contribute to completed ECTS.

```text
students ──< course_enrollments >── courses
    │                                  │
    └──< course_completions >──────────┤
                                       └──< teacher_course_assignments >── tutors
```

## Repository support

- `StudentRepository`: existing internal-ID/name search contracts remain
  unchanged; academic-number lookup provides contact for future authorized tools.
- `CourseRepository`: course code lookup, name/code search, list all, teachers.
- `AcademicRecordRepository`: student courses, course roster, student results,
  course results, optional PASSED/FAILED filtering.
- `TutorRepository`: tutor ID, name search, contact, courses taught, existing
  student assignments and notification recipients.

These repositories are intended for future MCP tools. Agents must continue to
access them only through the existing Agent → Gateway → MCP → Repository chain.

## Migration and demo data

- `005_extend_tutor_academic_data.sql` is additive, uses foreign keys, unique
  constraints, checks and lookup indexes, and preserves existing rows.
- `006_seed_tutor_academic_demo_data.sql` is idempotent and adds three fictional
  students, three courses, two fictional teachers, multiple enrollments, and a
  passed result, a failed result, and a teacher who teaches multiple courses.
  `.invalid` contact domains prevent accidental real delivery. A guarded
  PostgreSQL block supports both known historical `course_completions` shapes
  (with or without denormalized course code/name columns).

## Supported future queries

The repository layer can now retrieve/search students, courses and teachers;
list course rosters and student enrollments; list/filter passed and failed
results; and traverse teacher-course assignments. In-progress/not-completed
students are represented by enrollment rows without a passed completion.

Counts such as “how many passed DII101” should be derived from repository results
or implemented as a future optimized repository query when Issue #222 defines
the MCP response contract. No answer is hard-coded here.

## Backward compatibility

Existing integer student IDs, student numbers, existing profile/search payloads,
tutor assignments and table names are unchanged. All new contact fields and
completion course links are nullable. Contact is exposed only by new repository
methods, not silently added to existing unauthenticated MCP responses.
No MCP, gateway, agent, risk, dashboard, chat or Telegram public contract is
replaced. The only existing query change excludes explicit failed results from
completed ECTS while preserving legacy rows as passed.

## Deferred to #222–#230

- MCP academic search/query tools and response schemas;
- entity resolution and intent routing;
- academic data query agent and conversational context;
- tutor authorization policy for contact and roster exposure;
- natural-language responses and Telegram UX;
- production-specific backfill from legacy completion names/codes to `course_id`;
- optimized aggregate/count queries after consumer contracts are known.

## Verification

Focused migration and repository suite:

```text
36 passed
```

Affected MCP, academic service, dashboard, risk, agent and workflow suites:

```text
521 passed
```

Full backend suite:

```text
1116 passed, 2 failed, 1 warning
```

The same two E2E response-wording failures reproduce on untouched `origin/main`
with the current dependency resolution (9 other tests in that module pass).
They are unrelated to the data layer. The warning is a Starlette TestClient
deprecation warning from the resolved dependencies.

## Acceptance criteria mapping

- Existing schema/models/repositories audited: documented in the audit table.
- Tutor-query requirements documented: future query support and deferrals above.
- Existing structures reused: `students`, `tutors`, and `course_completions`.
- Missing fields/relationships added: contact, courses, enrollments, results and
  teacher-course assignments.
- Student/course relationships queryable: both directions in
  `AcademicRecordRepository`.
- Course result/completion queryable: student/course result methods with
  PASSED/FAILED filters; incomplete means enrollment without a passed result.
- Teacher/course relationships queryable: both directions across course and
  tutor repositories.
- Supported contact available: new explicit student-number and tutor lookup
  methods include email without changing existing public MCP payloads.
- Human-facing identifiers: existing `student_number` plus unique `course_code`.
- Repository ready for future MCP tools: new repository APIs remain below MCP.
- Connected development/test data: fictional multi-student/course/teacher seed,
  pass/fail/in-progress states, and repository fixtures.
- Proper migrations: additive PostgreSQL migrations 005 and 006.
- Backward compatibility: existing affected suites pass; legacy completions are
  treated as passed and existing public tool/agent contracts are unchanged.
- No duplicate academic source: course results extend `course_completions`; no
  parallel result table or duplicate Student/Teacher model was introduced.
