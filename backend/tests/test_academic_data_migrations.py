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
