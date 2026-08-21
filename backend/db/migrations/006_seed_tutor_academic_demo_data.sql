BEGIN;

-- Fictional, idempotent development data for Issue #221. Existing seed IDs are
-- not changed and no real personal data is used.
INSERT INTO students (
    student_number, name, email, group_name, programme, programme_code,
    start_date, status
)
VALUES
    ('DEMO22101', 'Elina Demo', 'elina.demo@example.invalid', 'DIN24',
     'Business IT', 'DIN2024S', DATE '2024-08-20', 'ACTIVE'),
    ('DEMO22102', 'Oskari Example', 'oskari.example@example.invalid', 'DIN24',
     'Business IT', 'DIN2024S', DATE '2024-08-20', 'ACTIVE'),
    ('DEMO22103', 'Sofia Sample', 'sofia.sample@example.invalid', 'DIN24',
     'Business IT', 'DIN2024S', DATE '2024-08-20', 'ACTIVE')
ON CONFLICT (student_number) DO UPDATE
SET email = EXCLUDED.email;

INSERT INTO tutors (display_name, email, is_active)
VALUES
    ('Anna Example', 'anna.example@example.invalid', TRUE),
    ('Matti Demo', 'matti.demo@example.invalid', TRUE)
ON CONFLICT DO NOTHING;

INSERT INTO courses (
    course_code, course_name, credits, programme_code, semester
)
VALUES
    ('DII101', 'Digital Innovation Foundations', 5.0, 'DIN2024S', 1),
    ('DBS24', 'Database Systems', 5.0, 'DIN2024S', 2),
    ('WEB24', 'Web Application Development', 5.0, 'DIN2024S', 2)
ON CONFLICT (course_code) DO UPDATE
SET course_name = EXCLUDED.course_name,
    credits = EXCLUDED.credits,
    programme_code = EXCLUDED.programme_code,
    semester = EXCLUDED.semester;

INSERT INTO course_enrollments (student_id, course_id, enrollment_status, enrolled_at)
SELECT student.id, course.id, values.enrollment_status, DATE '2024-08-20'
FROM (
    VALUES
        ('DEMO22101', 'DII101', 'COMPLETED'),
        ('DEMO22101', 'DBS24', 'IN_PROGRESS'),
        ('DEMO22102', 'DII101', 'COMPLETED'),
        ('DEMO22102', 'WEB24', 'IN_PROGRESS'),
        ('DEMO22103', 'DII101', 'IN_PROGRESS'),
        ('DEMO22103', 'DBS24', 'IN_PROGRESS')
) AS values(student_number, course_code, enrollment_status)
JOIN students AS student ON student.student_number = values.student_number
JOIN courses AS course ON course.course_code = values.course_code
ON CONFLICT (student_id, course_id) DO UPDATE
SET enrollment_status = EXCLUDED.enrollment_status;

-- course_completions is the existing progress/result source. Historical
-- deployments may or may not include denormalized course_code/course_name
-- columns, so seed the appropriate known shape without creating another result
-- table. Failed credits are excluded by ProgressRepository after migration.
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
            course.credits, course.semester, values.result_status,
            values.grade, values.completion_date
        FROM (
            VALUES
                ('DEMO22101', 'DII101', 'PASSED', '5', DATE '2025-05-20'),
                ('DEMO22102', 'DII101', 'FAILED', '0', DATE '2025-05-20'),
                ('DEMO22101', 'DBS24', 'PASSED', '4', DATE '2025-06-10'),
                ('DEMO22102', 'DBS24', 'FAILED', '0', DATE '2025-06-10')
        ) AS values(student_number, course_code, result_status, grade, completion_date)
        JOIN students AS student ON student.student_number = values.student_number
        JOIN courses AS course ON course.course_code = values.course_code
        WHERE NOT EXISTS (
            SELECT 1 FROM course_completions AS existing
            WHERE existing.student_id = student.id AND existing.course_id = course.id
        );
    ELSE
        INSERT INTO course_completions (
            student_id, course_id, credits, semester, result_status, grade,
            completion_date
        )
        SELECT
            student.id, course.id, course.credits, course.semester,
            values.result_status, values.grade, values.completion_date
        FROM (
            VALUES
                ('DEMO22101', 'DII101', 'PASSED', '5', DATE '2025-05-20'),
                ('DEMO22102', 'DII101', 'FAILED', '0', DATE '2025-05-20'),
                ('DEMO22101', 'DBS24', 'PASSED', '4', DATE '2025-06-10'),
                ('DEMO22102', 'DBS24', 'FAILED', '0', DATE '2025-06-10')
        ) AS values(student_number, course_code, result_status, grade, completion_date)
        JOIN students AS student ON student.student_number = values.student_number
        JOIN courses AS course ON course.course_code = values.course_code
        WHERE NOT EXISTS (
            SELECT 1 FROM course_completions AS existing
            WHERE existing.student_id = student.id AND existing.course_id = course.id
        );
    END IF;
END $$;

INSERT INTO teacher_course_assignments (tutor_id, course_id, assignment_role)
SELECT tutor.id, course.id, values.assignment_role
FROM (
    VALUES
        ('anna.example@example.invalid', 'DII101', 'LEAD_TEACHER'),
        ('anna.example@example.invalid', 'DBS24', 'TEACHER'),
        ('matti.demo@example.invalid', 'WEB24', 'LEAD_TEACHER')
) AS values(email, course_code, assignment_role)
JOIN tutors AS tutor ON LOWER(tutor.email) = LOWER(values.email)
JOIN courses AS course ON course.course_code = values.course_code
ON CONFLICT (tutor_id, course_id) DO UPDATE
SET assignment_role = EXCLUDED.assignment_role;

COMMIT;
