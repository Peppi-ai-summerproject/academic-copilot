# Student groups and academic structure

The canonical academic hierarchy is `degree_programmes` → `student_groups` →
`students`. A student references one cohort through `students.group_id`.
`students.group_name`, `students.programme`, and `students.programme_code` remain
available as compatibility fields for existing search, reporting, dashboard,
and MCP contracts.

Groups and courses have a many-to-many relationship through
`student_group_courses`. This permits a cohort to share courses with other
cohorts and allows its curriculum to evolve without changing course identity.
Courses remain independent teaching units. Their many-to-many teacher
relationship continues to use `teacher_course_assignments`; enrollments and
results continue to use `course_enrollments` and `course_completions`.

Migration 008 corrects the historical Issue #221 demo data. DIN24 becomes the
Business IT cohort, while Digital Innovation Foundations uses course code
DII101. Existing foreign-key relationships referencing the obsolete DIN24
course are migrated to DII101 before that course row is removed. Enrollment and
teacher-assignment conflicts retain the existing DII101 relationship. For
completion records, no domain authority rule exists: identical duplicates are
collapsed, but any difference in stored academic fields aborts the transaction
for explicit operator resolution, preserving both source records. The migration
is intentionally not run automatically;
deployment operators should apply it through the project's existing ordered SQL
migration process and take the normal database backup first.

Group-aware MCP entity resolution and conversational GROUP intent are outside
this data-layer issue. `StudentGroupRepository` provides the canonical read
boundary for that follow-up work.
