BEGIN;

-- Add representative DBS24 results for the DIN24 demo cohort. Existing
-- academic records are authoritative: this migration inserts only when the
-- canonical student/course pair has no completion and never updates or deletes.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'course_completions' AND column_name = 'course_code'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'course_completions' AND column_name = 'course_name'
    ) THEN
        INSERT INTO course_completions (
            student_id, course_id, course_code, course_name, credits, semester,
            result_status, grade, completion_date
        )
        SELECT
            student.id, course.id, course.course_code, course.course_name,
            course.credits, course.semester, demo.result_status,
            demo.grade, demo.completion_date
        FROM (
            VALUES
                ('DEMO22101', 'DBS24', 'PASSED', '4', DATE '2025-06-10'),
                ('DEMO22102', 'DBS24', 'FAILED', '0', DATE '2025-06-10')
        ) AS demo(student_number, course_code, result_status, grade, completion_date)
        INNER JOIN students AS student
            ON student.student_number = demo.student_number
        INNER JOIN courses AS course
            ON course.course_code = demo.course_code
        WHERE NOT EXISTS (
            SELECT 1
            FROM course_completions AS existing
            WHERE existing.student_id = student.id
              AND (
                  existing.course_id = course.id
                  OR LOWER(existing.course_code) = LOWER(course.course_code)
              )
        )
        ON CONFLICT (student_id, course_id) WHERE course_id IS NOT NULL
        DO NOTHING;
    ELSE
        INSERT INTO course_completions (
            student_id, course_id, credits, semester, result_status, grade,
            completion_date
        )
        SELECT
            student.id, course.id, course.credits, course.semester,
            demo.result_status, demo.grade, demo.completion_date
        FROM (
            VALUES
                ('DEMO22101', 'DBS24', 'PASSED', '4', DATE '2025-06-10'),
                ('DEMO22102', 'DBS24', 'FAILED', '0', DATE '2025-06-10')
        ) AS demo(student_number, course_code, result_status, grade, completion_date)
        INNER JOIN students AS student
            ON student.student_number = demo.student_number
        INNER JOIN courses AS course
            ON course.course_code = demo.course_code
        WHERE NOT EXISTS (
            SELECT 1
            FROM course_completions AS existing
            WHERE existing.student_id = student.id
              AND existing.course_id = course.id
        )
        ON CONFLICT (student_id, course_id) WHERE course_id IS NOT NULL
        DO NOTHING;
    END IF;
END $$;

COMMIT;
