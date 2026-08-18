-- Issue #222: canonical, tutor-facing academic discovery records.
ALTER TABLE students ADD COLUMN IF NOT EXISTS email VARCHAR(255);
UPDATE students
SET email = LOWER(student_number) || '@students.peppi.example'
WHERE email IS NULL;

CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    course_code VARCHAR(50) NOT NULL UNIQUE,
    course_name VARCHAR(255) NOT NULL,
    credits INTEGER NOT NULL,
    programme VARCHAR(255),
    semester INTEGER
);

-- The existing completion history is the source of truth for the initial catalogue.
INSERT INTO courses (course_code, course_name, credits, semester)
SELECT course_code, MIN(course_name), MIN(credits), MIN(semester)
FROM course_completions
WHERE course_code IS NOT NULL AND course_name IS NOT NULL
GROUP BY course_code
ON CONFLICT (course_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS teachers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    role VARCHAR(100)
);

INSERT INTO teachers (name, email, role)
VALUES
    ('Anna Korhonen', 'anna.korhonen@peppi.example', 'Senior Lecturer'),
    ('Matti Virtanen', 'matti.virtanen@peppi.example', 'Lecturer'),
    ('Sari Laine', 'sari.laine@peppi.example', 'Programme Coordinator')
ON CONFLICT (email) DO NOTHING;
