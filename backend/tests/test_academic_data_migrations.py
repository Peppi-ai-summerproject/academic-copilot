from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = PROJECT_ROOT / "backend" / "db" / "migrations"


def test_schema_migration_reuses_existing_student_tutor_and_completion_tables() -> None:
    sql = (MIGRATIONS / "005_extend_tutor_academic_data.sql").read_text()

    assert "ALTER TABLE students" in sql
    assert "ALTER TABLE tutors" in sql
    assert "ALTER TABLE course_completions" in sql
    assert "CREATE TABLE IF NOT EXISTS courses" in sql
    assert "CREATE TABLE IF NOT EXISTS course_enrollments" in sql
    assert "CREATE TABLE IF NOT EXISTS teacher_course_assignments" in sql
    assert "CREATE TABLE course_results" not in sql


def test_schema_migration_has_search_and_relationship_constraints() -> None:
    sql = (MIGRATIONS / "005_extend_tutor_academic_data.sql").read_text()

    assert "course_code VARCHAR(50) NOT NULL UNIQUE" in sql
    assert "UNIQUE (student_id, course_id)" in sql
    assert "PRIMARY KEY (tutor_id, course_id)" in sql
    assert "result_status IN ('PASSED', 'FAILED')" in sql
    assert "ux_students_email_lower" in sql
    assert "ux_tutors_email_lower" in sql


def test_demo_seed_is_fictional_connected_and_idempotent() -> None:
    sql = (MIGRATIONS / "006_seed_tutor_academic_demo_data.sql").read_text()

    assert "example.invalid" in sql
    assert "DEMO22101" in sql
    assert "DEMO22102" in sql
    assert "DEMO22103" in sql
    assert "INSERT INTO courses" in sql
    assert "INSERT INTO course_enrollments" in sql
    assert "INSERT INTO course_completions" in sql
    assert "INSERT INTO teacher_course_assignments" in sql
    assert "'PASSED'" in sql
    assert "'FAILED'" in sql
    assert "ON CONFLICT" in sql


def test_student_group_migration_defines_canonical_academic_structure() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS degree_programmes" in sql
    assert "programme_code VARCHAR(50) NOT NULL UNIQUE" in sql
    assert "CREATE TABLE IF NOT EXISTS student_groups" in sql
    assert "group_code VARCHAR(50) NOT NULL UNIQUE" in sql
    assert "REFERENCES degree_programmes(id) ON DELETE RESTRICT" in sql
    assert "ADD COLUMN IF NOT EXISTS group_id" in sql
    assert "REFERENCES student_groups(id)" in sql
    assert "CREATE TABLE IF NOT EXISTS student_group_courses" in sql
    assert "PRIMARY KEY (group_id, course_id)" in sql


def test_student_group_migration_is_idempotent_and_preserves_relationships() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert sql.count("CREATE TABLE IF NOT EXISTS") >= 3
    assert "IF NOT EXISTS (" in sql
    assert "ON CONFLICT (LOWER(group_code)) DO UPDATE" in sql
    assert "ON CONFLICT (group_id, course_id) DO NOTHING" in sql
    assert "UPDATE course_completions" in sql
    assert "INSERT INTO course_enrollments" in sql
    assert "INSERT INTO teacher_course_assignments" in sql
    assert "DELETE FROM courses WHERE id = incorrect_course_id" in sql


def test_demo_seed_and_correction_represent_din24_only_as_a_group() -> None:
    seed = (MIGRATIONS / "006_seed_tutor_academic_demo_data.sql").read_text()
    migration = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "('DIN24', 'Digital Innovation Foundations'" not in seed
    assert "('DII101', 'Digital Innovation Foundations'" in seed
    assert seed.count("'DIN24'") == 3  # compatibility group_name for demo students
    assert "SELECT 'DIN24', 'Digital Innovation 2024 cohort'" in migration
    assert "course.course_code IN ('DII101', 'DBS24', 'WEB24')" in migration
    assert "student_number IN ('DEMO22101', 'DEMO22102', 'DEMO22103')" in migration


def test_case_insensitive_indexes_are_used_as_upsert_conflict_targets() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "ON CONFLICT (LOWER(programme_code)) DO UPDATE" in sql
    assert "ON CONFLICT (LOWER(programme_code)) DO NOTHING" in sql
    assert "ON CONFLICT (LOWER(group_code)) DO NOTHING" in sql
    assert "ON CONFLICT (LOWER(group_code)) DO UPDATE" in sql
    assert "ON CONFLICT (programme_code)" not in sql
    assert "ON CONFLICT (group_code)" not in sql
    assert "GROUP BY UPPER(BTRIM(student.programme_code))" in sql
    assert "DISTINCT ON (LOWER(BTRIM(student.group_name)))" in sql


def test_case_variant_rows_are_matched_without_creating_duplicate_codes() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "LOWER(programme.programme_code) = LOWER('DIN2024S')" in sql
    assert "LOWER(student_group.group_code) = LOWER('DIN24')" in sql
    assert "ux_degree_programmes_code_lower" in sql
    assert "ux_student_groups_code_lower" in sql


def test_completion_conflict_policy_rekeys_a_single_obsolete_record() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "UPDATE course_completions" in sql
    assert "SET course_id = replacement_course_id" in sql
    assert "WHERE course_id = incorrect_course_id" in sql


def test_completion_conflict_policy_leaves_a_sole_replacement_record_untouched() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "WHERE incorrect.course_id = incorrect_course_id" in sql
    assert "replacement.course_id = replacement_course_id" in sql
    assert "DELETE FROM courses WHERE id = incorrect_course_id" in sql


def test_completion_conflict_policy_removes_only_identical_duplicates() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "IS NOT DISTINCT FROM" in sql
    assert "DELETE FROM course_completions AS incorrect" in sql
    assert "ARRAY['id', 'course_id', 'course_code', 'course_name']" in sql


def test_completion_conflict_policy_aborts_on_any_meaningful_difference() -> None:
    sql = (
        MIGRATIONS / "008_add_student_groups_and_academic_structure.sql"
    ).read_text()

    assert "IS DISTINCT FROM" in sql
    assert "RAISE EXCEPTION USING" in sql
    assert "ERRCODE = '23514'" in sql
    assert "require manual resolution" in sql
    assert "to_jsonb(incorrect)" in sql
    assert "to_jsonb(replacement)" in sql
