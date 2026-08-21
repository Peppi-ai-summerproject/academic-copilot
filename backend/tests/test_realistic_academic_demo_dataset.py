import re
from pathlib import Path
from unittest.mock import Mock

from app.services.progress_service import ProgressService
from app.services.risk_policy import progress_risk_factors


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend" / "db" / "migrations" / "010_seed_realistic_academic_demo_dataset.sql"


def _sql() -> str:
    return MIGRATION.read_text()


def _completion_rows() -> list[tuple[str, str, str, str]]:
    return re.findall(
        r"\('(DEMO252\d{2})', '([A-Z0-9]+)', '(PASSED|FAILED)', '([0-5])', DATE",
        _sql(),
    )


def test_dataset_defines_six_additional_canonical_din24_students() -> None:
    sql = _sql()
    expected = {
        "DEMO25201": "Aava Achiever",
        "DEMO25202": "Niko Normal",
        "DEMO25203": "Petra Partial",
        "DEMO25204": "Matias Multiple",
        "DEMO25205": "Liisa Delayed",
        "DEMO25206": "Eero Mixed",
    }
    for number, name in expected.items():
        assert f"('{number}', '{name}'" in sql
    assert "LOWER(student_group.group_code) = LOWER('DIN24')" in sql
    assert "student.student_number = demo.student_number" not in sql
    assert "ON CONFLICT (student_number) DO NOTHING" in sql


def test_dataset_associates_supporting_courses_with_canonical_group() -> None:
    sql = _sql()
    for code in ("BUS101", "PRG101", "UXD101", "NET101", "PRJ101", "DAT102", "API102", "SEC102", "CLD102"):
        assert f"('{code}'," in sql
    assert "INSERT INTO student_group_courses" in sql
    assert "ON CONFLICT (group_id, course_id) DO NOTHING" in sql


def test_result_matrix_has_required_dbs_dii_and_web_diversity() -> None:
    rows = _completion_rows()
    dbs_passed = {student for student, course, status, _ in rows if course == "DBS24" and status == "PASSED"}
    dbs_failed = {student for student, course, status, _ in rows if course == "DBS24" and status == "FAILED"}
    dii_statuses = {status for _, course, status, _ in rows if course == "DII101"}
    web_statuses = {status for _, course, status, _ in rows if course == "WEB24"}

    assert dbs_passed == {"DEMO25201", "DEMO25206"}
    assert dbs_failed == {"DEMO25203", "DEMO25204"}
    assert dii_statuses == {"PASSED"}
    assert web_statuses == {"PASSED", "FAILED"}
    assert any(grade == "0" for _, _, status, grade in rows if status == "FAILED")


def test_known_existing_and_new_records_produce_useful_course_analytics() -> None:
    rows = _completion_rows()
    counts = {
        (course, status): sum(1 for _, row_course, row_status, _ in rows if row_course == course and row_status == status)
        for course in ("DBS24", "DII101", "WEB24")
        for status in ("PASSED", "FAILED")
    }
    # Add immutable Issue #221/#249 records: Elina PASSED and Oskari FAILED
    # for both DBS24 and DII101. Sofia intentionally contributes no completion.
    counts[("DBS24", "PASSED")] += 1
    counts[("DBS24", "FAILED")] += 1
    counts[("DII101", "PASSED")] += 1
    counts[("DII101", "FAILED")] += 1

    assert counts[("DBS24", "PASSED")] == 3
    assert counts[("DBS24", "FAILED")] == 3
    assert counts[("DII101", "PASSED")] == 7
    assert counts[("DII101", "FAILED")] == 1
    assert counts[("WEB24", "PASSED")] == 1
    assert counts[("WEB24", "FAILED")] == 2


def test_existing_authoritative_results_are_preserved_by_additive_migration() -> None:
    sql = _sql()
    assert "DEMO22101" not in sql
    assert "DEMO22102" not in sql
    assert "DEMO22103" not in sql
    assert "UPDATE course_completions" not in sql
    assert "DELETE FROM" not in sql


def test_enrollment_without_completion_remains_representable() -> None:
    sql = _sql()
    rows = _completion_rows()
    liisa_courses = {course for student, course, _, _ in rows if student == "DEMO25205"}
    assert liisa_courses == {"DII101", "BUS101", "PRG101"}
    assert "THEN 'IN_PROGRESS'" in sql
    assert "INNER JOIN student_group_courses AS association" in sql


def test_migration_is_idempotent_and_preserves_conflicting_records() -> None:
    sql = _sql()
    assert "WHERE NOT EXISTS" in sql
    assert "ON CONFLICT (course_code) DO NOTHING" in sql
    assert "ON CONFLICT (student_id, course_id) DO NOTHING" in sql
    assert "ON CONFLICT (student_id, course_id) WHERE course_id IS NOT NULL" in sql
    assert "DO NOTHING" in sql
    assert "UPDATE course_completions" not in sql
    assert "DELETE FROM course_completions" not in sql


def test_persona_progress_and_risk_follow_existing_rules() -> None:
    rows = _completion_rows()
    semesters = {"DII101": 1, "BUS101": 1, "PRG101": 1, "UXD101": 1, "NET101": 1, "PRJ101": 1,
                 "DBS24": 2, "WEB24": 2, "DAT102": 2, "API102": 2, "SEC102": 2, "CLD102": 2}
    expected = {
        "DEMO25201": (60, 2, "ON_TRACK", None),
        "DEMO25202": (30, 1, "ON_TRACK", None),
        "DEMO25203": (25, 1, "BEHIND", "LOW"),
        "DEMO25204": (5, 1, "BEHIND", "LOW"),
        "DEMO25205": (15, 1, "BEHIND", "LOW"),
        "DEMO25206": (55, 2, "BEHIND", "LOW"),
    }
    for student_number, (ects, semester, status, risk) in expected.items():
        passed = [(course, state) for student, course, state, _ in rows if student == student_number and state == "PASSED"]
        repository = Mock()
        repository.get_student_progress_data.return_value = {
            "student_id": 1, "student_number": student_number, "name": student_number,
            "programme": "Business IT", "completed_ects": len(passed) * 5,
            "current_semester": max((semesters[course] for course, _ in passed), default=1),
        }
        repository.get_expected_ects.side_effect = lambda _, current: 30 * current
        progress = ProgressService(repository).get_progress(1)["progress"]
        factors = progress_risk_factors(progress)
        assert (progress["completed_ects"], progress["current_semester"], progress["status"]) == (ects, semester, status)
        assert (factors[0]["level"] if factors else None) == risk
