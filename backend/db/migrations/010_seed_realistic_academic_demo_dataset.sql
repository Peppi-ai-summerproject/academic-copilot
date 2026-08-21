BEGIN;

-- Issue #252: deterministic fictional DIN24 personas. Existing rows are
-- authoritative; every insert is additive and conflicts are left untouched.
INSERT INTO courses (course_code, course_name, credits, programme_code, semester)
VALUES
    ('BUS101', 'Business Foundations', 5.0, 'DIN2024S', 1),
    ('PRG101', 'Programming Basics', 5.0, 'DIN2024S', 1),
    ('UXD101', 'User Experience Design', 5.0, 'DIN2024S', 1),
    ('NET101', 'Network Fundamentals', 5.0, 'DIN2024S', 1),
    ('PRJ101', 'Project Skills', 5.0, 'DIN2024S', 1),
    ('DAT102', 'Data Analytics', 5.0, 'DIN2024S', 2),
    ('API102', 'API Development', 5.0, 'DIN2024S', 2),
    ('SEC102', 'Application Security', 5.0, 'DIN2024S', 2),
    ('CLD102', 'Cloud Fundamentals', 5.0, 'DIN2024S', 2)
ON CONFLICT (course_code) DO NOTHING;

INSERT INTO student_group_courses (group_id, course_id)
SELECT student_group.id, course.id
FROM student_groups AS student_group
INNER JOIN courses AS course
    ON course.course_code IN (
        'BUS101', 'PRG101', 'UXD101', 'NET101', 'PRJ101',
        'DAT102', 'API102', 'SEC102', 'CLD102'
    )
WHERE LOWER(student_group.group_code) = LOWER('DIN24')
ON CONFLICT (group_id, course_id) DO NOTHING;

INSERT INTO students (
    student_number, name, email, group_name, programme, programme_code,
    start_date, status, group_id
)
SELECT
    demo.student_number, demo.name, demo.email, student_group.group_code,
    'Business IT', 'DIN2024S', DATE '2024-08-20', 'ACTIVE', student_group.id
FROM (
    VALUES
        ('DEMO25201', 'Aava Achiever', 'aava.achiever@example.invalid'),
        ('DEMO25202', 'Niko Normal', 'niko.normal@example.invalid'),
        ('DEMO25203', 'Petra Partial', 'petra.partial@example.invalid'),
        ('DEMO25204', 'Matias Multiple', 'matias.multiple@example.invalid'),
        ('DEMO25205', 'Liisa Delayed', 'liisa.delayed@example.invalid'),
        ('DEMO25206', 'Eero Mixed', 'eero.mixed@example.invalid')
) AS demo(student_number, name, email)
INNER JOIN student_groups AS student_group
    ON LOWER(student_group.group_code) = LOWER('DIN24')
WHERE NOT EXISTS (
    SELECT 1 FROM students AS existing
    WHERE existing.student_number = demo.student_number
)
ON CONFLICT (student_number) DO NOTHING;

CREATE TEMPORARY TABLE issue_252_completion_seed (
    student_number VARCHAR(50) NOT NULL,
    course_code VARCHAR(50) NOT NULL,
    result_status VARCHAR(20) NOT NULL,
    grade VARCHAR(20) NOT NULL,
    completion_date DATE NOT NULL,
    PRIMARY KEY (student_number, course_code)
) ON COMMIT DROP;

INSERT INTO issue_252_completion_seed VALUES
    -- Aava: all 60 ECTS across semesters 1-2, excellent and ON_TRACK.
    ('DEMO25201', 'DII101', 'PASSED', '5', DATE '2025-01-15'),
    ('DEMO25201', 'BUS101', 'PASSED', '5', DATE '2025-01-16'),
    ('DEMO25201', 'PRG101', 'PASSED', '5', DATE '2025-01-17'),
    ('DEMO25201', 'UXD101', 'PASSED', '5', DATE '2025-01-18'),
    ('DEMO25201', 'NET101', 'PASSED', '4', DATE '2025-01-19'),
    ('DEMO25201', 'PRJ101', 'PASSED', '5', DATE '2025-01-20'),
    ('DEMO25201', 'DBS24', 'PASSED', '5', DATE '2025-06-10'),
    ('DEMO25201', 'WEB24', 'PASSED', '5', DATE '2025-06-11'),
    ('DEMO25201', 'DAT102', 'PASSED', '4', DATE '2025-06-12'),
    ('DEMO25201', 'API102', 'PASSED', '5', DATE '2025-06-13'),
    ('DEMO25201', 'SEC102', 'PASSED', '4', DATE '2025-06-14'),
    ('DEMO25201', 'CLD102', 'PASSED', '5', DATE '2025-06-15'),
    -- Niko: complete semester 1 at exactly 30 ECTS, normal ON_TRACK.
    ('DEMO25202', 'DII101', 'PASSED', '3', DATE '2025-01-15'),
    ('DEMO25202', 'BUS101', 'PASSED', '3', DATE '2025-01-16'),
    ('DEMO25202', 'PRG101', 'PASSED', '4', DATE '2025-01-17'),
    ('DEMO25202', 'UXD101', 'PASSED', '3', DATE '2025-01-18'),
    ('DEMO25202', 'NET101', 'PASSED', '3', DATE '2025-01-19'),
    ('DEMO25202', 'PRJ101', 'PASSED', '4', DATE '2025-01-20'),
    -- Petra: 25 ECTS and one failed semester-2 course.
    ('DEMO25203', 'DII101', 'PASSED', '3', DATE '2025-01-15'),
    ('DEMO25203', 'BUS101', 'PASSED', '3', DATE '2025-01-16'),
    ('DEMO25203', 'PRG101', 'PASSED', '3', DATE '2025-01-17'),
    ('DEMO25203', 'UXD101', 'PASSED', '2', DATE '2025-01-18'),
    ('DEMO25203', 'NET101', 'PASSED', '3', DATE '2025-01-19'),
    ('DEMO25203', 'DBS24', 'FAILED', '0', DATE '2025-06-10'),
    -- Matias: low credits with multiple genuine failures.
    ('DEMO25204', 'DII101', 'PASSED', '2', DATE '2025-01-15'),
    ('DEMO25204', 'DBS24', 'FAILED', '0', DATE '2025-06-10'),
    ('DEMO25204', 'WEB24', 'FAILED', '0', DATE '2025-06-11'),
    -- Liisa: delayed, with 15 ECTS and outstanding enrollments.
    ('DEMO25205', 'DII101', 'PASSED', '3', DATE '2025-01-15'),
    ('DEMO25205', 'BUS101', 'PASSED', '3', DATE '2025-01-16'),
    ('DEMO25205', 'PRG101', 'PASSED', '3', DATE '2025-01-17'),
    -- Eero: mixed semester 2, 55 ECTS and a WEB24 failure.
    ('DEMO25206', 'DII101', 'PASSED', '4', DATE '2025-01-15'),
    ('DEMO25206', 'BUS101', 'PASSED', '4', DATE '2025-01-16'),
    ('DEMO25206', 'PRG101', 'PASSED', '4', DATE '2025-01-17'),
    ('DEMO25206', 'UXD101', 'PASSED', '3', DATE '2025-01-18'),
    ('DEMO25206', 'NET101', 'PASSED', '4', DATE '2025-01-19'),
    ('DEMO25206', 'PRJ101', 'PASSED', '4', DATE '2025-01-20'),
    ('DEMO25206', 'DBS24', 'PASSED', '4', DATE '2025-06-10'),
    ('DEMO25206', 'WEB24', 'FAILED', '0', DATE '2025-06-11'),
    ('DEMO25206', 'DAT102', 'PASSED', '3', DATE '2025-06-12'),
    ('DEMO25206', 'API102', 'PASSED', '4', DATE '2025-06-13'),
    ('DEMO25206', 'SEC102', 'PASSED', '3', DATE '2025-06-14'),
    ('DEMO25206', 'CLD102', 'PASSED', '4', DATE '2025-06-15');

-- Enroll every new persona in the canonical DIN24 curriculum. A completion
-- controls result semantics; rows without one remain IN_PROGRESS.
INSERT INTO course_enrollments (
    student_id, course_id, enrollment_status, enrolled_at
)
SELECT
    student.id,
    course.id,
    CASE WHEN completion.student_number IS NULL THEN 'IN_PROGRESS'
         ELSE 'COMPLETED' END,
    DATE '2024-08-20'
FROM students AS student
INNER JOIN student_groups AS student_group ON student_group.id = student.group_id
INNER JOIN student_group_courses AS association
    ON association.group_id = student_group.id
INNER JOIN courses AS course ON course.id = association.course_id
LEFT JOIN issue_252_completion_seed AS completion
    ON completion.student_number = student.student_number
   AND completion.course_code = course.course_code
WHERE student.student_number IN (
    'DEMO25201', 'DEMO25202', 'DEMO25203',
    'DEMO25204', 'DEMO25205', 'DEMO25206'
)
  AND LOWER(student_group.group_code) = LOWER('DIN24')
ON CONFLICT (student_id, course_id) DO NOTHING;

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
        SELECT student.id, course.id, course.course_code, course.course_name,
               course.credits, course.semester, seed.result_status,
               seed.grade, seed.completion_date
        FROM issue_252_completion_seed AS seed
        INNER JOIN students AS student
            ON student.student_number = seed.student_number
        INNER JOIN courses AS course ON course.course_code = seed.course_code
        WHERE NOT EXISTS (
            SELECT 1 FROM course_completions AS existing
            WHERE existing.student_id = student.id
              AND (existing.course_id = course.id
                   OR LOWER(existing.course_code) = LOWER(course.course_code))
        )
        ON CONFLICT (student_id, course_id) WHERE course_id IS NOT NULL
        DO NOTHING;
    ELSE
        INSERT INTO course_completions (
            student_id, course_id, credits, semester, result_status, grade,
            completion_date
        )
        SELECT student.id, course.id, course.credits, course.semester,
               seed.result_status, seed.grade, seed.completion_date
        FROM issue_252_completion_seed AS seed
        INNER JOIN students AS student
            ON student.student_number = seed.student_number
        INNER JOIN courses AS course ON course.course_code = seed.course_code
        WHERE NOT EXISTS (
            SELECT 1 FROM course_completions AS existing
            WHERE existing.student_id = student.id
              AND existing.course_id = course.id
        )
        ON CONFLICT (student_id, course_id) WHERE course_id IS NOT NULL
        DO NOTHING;
    END IF;
END $$;

COMMIT;
