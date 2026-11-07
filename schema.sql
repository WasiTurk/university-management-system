-- University Management System: SQLite schema
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS departments (
    id   INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS faculty (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    designation TEXT NOT NULL DEFAULT 'Lecturer'
                CHECK (designation IN ('Lecturer','Assistant Professor','Associate Professor','Professor')),
    dept_id     INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY,
    roll_no     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    dept_id     INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    enroll_year INTEGER NOT NULL CHECK (enroll_year BETWEEN 1990 AND 2100),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courses (
    id         INTEGER PRIMARY KEY,
    code       TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    credits    INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 6),
    capacity   INTEGER NOT NULL DEFAULT 40 CHECK (capacity > 0),
    dept_id    INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    faculty_id INTEGER REFERENCES faculty(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
    id           INTEGER PRIMARY KEY,
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id    INTEGER NOT NULL REFERENCES courses(id)  ON DELETE CASCADE,
    semester     TEXT NOT NULL,                       -- e.g. 'Fall 2026'
    marks        REAL CHECK (marks IS NULL OR marks BETWEEN 0 AND 100),
    letter       TEXT,
    grade_points REAL CHECK (grade_points IS NULL OR grade_points BETWEEN 0 AND 4),
    enrolled_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, course_id, semester)
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    salt          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin','faculty','student')),
    ref_id        INTEGER,          -- students.id or faculty.id depending on role
    active        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    action   TEXT NOT NULL,
    detail   TEXT,
    ts       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_enroll_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enroll_course  ON enrollments(course_id);
CREATE INDEX IF NOT EXISTS idx_students_dept  ON students(dept_id);
CREATE INDEX IF NOT EXISTS idx_courses_fac    ON courses(faculty_id);

-- Business rule: a course cannot exceed its capacity in a given semester
CREATE TRIGGER IF NOT EXISTS trg_enroll_capacity
BEFORE INSERT ON enrollments
WHEN (SELECT COUNT(*) FROM enrollments
      WHERE course_id = NEW.course_id AND semester = NEW.semester)
     >= (SELECT capacity FROM courses WHERE id = NEW.course_id)
BEGIN
    SELECT RAISE(ABORT, 'Course is full');
END;

-- Business rule: removing a student/faculty also removes their login
CREATE TRIGGER IF NOT EXISTS trg_student_delete_user
AFTER DELETE ON students
BEGIN
    DELETE FROM users WHERE role = 'student' AND ref_id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_faculty_delete_user
AFTER DELETE ON faculty
BEGIN
    DELETE FROM users WHERE role = 'faculty' AND ref_id = OLD.id;
END;

-- Reporting views
CREATE VIEW IF NOT EXISTS v_student_gpa AS
SELECT s.id AS student_id, s.roll_no, s.name, s.dept_id,
       COUNT(e.id)                     AS graded_courses,
       COALESCE(SUM(c.credits), 0)     AS credits_earned,
       ROUND(SUM(e.grade_points * c.credits) * 1.0 / NULLIF(SUM(c.credits), 0), 2) AS gpa
FROM students s
LEFT JOIN enrollments e ON e.student_id = s.id AND e.marks IS NOT NULL
LEFT JOIN courses c     ON c.id = e.course_id
GROUP BY s.id;

CREATE VIEW IF NOT EXISTS v_course_stats AS
SELECT c.id AS course_id, c.code, c.title, c.capacity, c.faculty_id,
       COUNT(e.id)                                        AS enrolled,
       ROUND(AVG(e.marks), 1)                             AS avg_marks,
       ROUND(100.0 * SUM(CASE WHEN e.letter IS NOT NULL AND e.letter <> 'F' THEN 1 ELSE 0 END)
             / NULLIF(COUNT(e.marks), 0), 1)              AS pass_rate
FROM courses c
LEFT JOIN enrollments e ON e.course_id = c.id
GROUP BY c.id;
