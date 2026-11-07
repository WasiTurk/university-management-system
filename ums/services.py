"""Business logic. Every public function enforces role-based permissions."""
import sqlite3
from functools import wraps

from .auth import PermissionDenied, create_user

GRADE_SCALE = [  # (min marks, letter, grade points)
    (85, "A", 4.0), (80, "A-", 3.7), (75, "B+", 3.3), (70, "B", 3.0),
    (65, "B-", 2.7), (60, "C+", 2.3), (55, "C", 2.0), (50, "D", 1.0), (0, "F", 0.0),
]


def letter_grade(marks: float):
    for cutoff, letter, points in GRADE_SCALE:
        if marks >= cutoff:
            return letter, points


def require(permission):
    def deco(fn):
        @wraps(fn)
        def wrapper(conn, session, *a, **kw):
            if not session.can(permission):
                raise PermissionDenied(
                    f"Role '{session.role}' lacks permission '{permission}'")
            return fn(conn, session, *a, **kw)
        return wrapper
    return deco


def audit(conn, session, action, detail=""):
    conn.execute("INSERT INTO audit_log(username, action, detail) VALUES (?,?,?)",
                 (session.username, action, detail))


def _rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def _integrity(fn):
    """Turn raw SQLite errors into readable ValueErrors and roll back."""
    @wraps(fn)
    def wrapper(conn, *a, **kw):
        try:
            return fn(conn, *a, **kw)
        except sqlite3.IntegrityError as e:
            conn.rollback()
            msg = str(e)
            if "Course is full" in msg:
                raise ValueError("Course is full") from e
            if "UNIQUE" in msg:
                raise ValueError("A record with that unique value already exists") from e
            if "FOREIGN KEY" in msg:
                raise ValueError("Related record not found or still in use") from e
            raise ValueError(msg) from e
    return wrapper


# ---------------------------------------------------------------- departments
@require("manage_departments")
@_integrity
def add_department(conn, s, code, name):
    cur = conn.execute("INSERT INTO departments(code, name) VALUES (?,?)", (code.upper(), name))
    audit(conn, s, "ADD_DEPARTMENT", code)
    conn.commit()
    return cur.lastrowid


def list_departments(conn):
    return _rows(conn.execute("SELECT * FROM departments ORDER BY name"))


# ------------------------------------------------------------------- students
@require("manage_students")
@_integrity
def add_student(conn, s, roll_no, name, email, dept_id, enroll_year, password="student123"):
    cur = conn.execute(
        "INSERT INTO students(roll_no, name, email, dept_id, enroll_year) VALUES (?,?,?,?,?)",
        (roll_no, name, email, dept_id, enroll_year))
    create_user(conn, roll_no.lower(), password, "student", cur.lastrowid)
    audit(conn, s, "ADD_STUDENT", roll_no)
    conn.commit()
    return cur.lastrowid


@require("view_all_students")
def list_students(conn, s, search=None, dept_id=None):
    sql = ("SELECT st.id, st.roll_no, st.name, st.email, d.code AS dept, st.enroll_year "
           "FROM students st JOIN departments d ON d.id = st.dept_id WHERE 1=1")
    params = []
    if search:
        sql += " AND (st.name LIKE ? OR st.roll_no LIKE ? OR st.email LIKE ?)"
        params += [f"%{search}%"] * 3
    if dept_id:
        sql += " AND st.dept_id = ?"
        params.append(dept_id)
    return _rows(conn.execute(sql + " ORDER BY st.roll_no", params))


@require("manage_students")
@_integrity
def update_student(conn, s, student_id, **fields):
    allowed = {"name", "email", "dept_id", "enroll_year"}
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Cannot update fields: {', '.join(sorted(bad))}")
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE students SET {sets} WHERE id = ?", (*fields.values(), student_id))
    audit(conn, s, "UPDATE_STUDENT", f"{student_id}: {sorted(fields)}")
    conn.commit()


@require("manage_students")
def delete_student(conn, s, student_id):
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    audit(conn, s, "DELETE_STUDENT", str(student_id))
    conn.commit()


@require("view_own_profile")
def my_profile(conn, s):
    row = conn.execute(
        "SELECT st.roll_no, st.name, st.email, d.name AS department, st.enroll_year, "
        "g.gpa, g.credits_earned FROM students st "
        "JOIN departments d ON d.id = st.dept_id "
        "JOIN v_student_gpa g ON g.student_id = st.id WHERE st.id = ?", (s.ref_id,)).fetchone()
    return dict(row) if row else None


# -------------------------------------------------------------------- faculty
@require("manage_faculty")
@_integrity
def add_faculty(conn, s, name, email, dept_id, designation="Lecturer", password="faculty123"):
    cur = conn.execute(
        "INSERT INTO faculty(name, email, dept_id, designation) VALUES (?,?,?,?)",
        (name, email, dept_id, designation))
    create_user(conn, email.split("@")[0].lower(), password, "faculty", cur.lastrowid)
    audit(conn, s, "ADD_FACULTY", email)
    conn.commit()
    return cur.lastrowid


@require("manage_faculty")
def list_faculty(conn, s):
    return _rows(conn.execute(
        "SELECT f.id, f.name, f.email, f.designation, d.code AS dept "
        "FROM faculty f JOIN departments d ON d.id = f.dept_id ORDER BY f.name"))


# -------------------------------------------------------------------- courses
@require("manage_courses")
@_integrity
def add_course(conn, s, code, title, credits, dept_id, faculty_id=None, capacity=40):
    cur = conn.execute(
        "INSERT INTO courses(code, title, credits, capacity, dept_id, faculty_id) "
        "VALUES (?,?,?,?,?,?)", (code.upper(), title, credits, capacity, dept_id, faculty_id))
    audit(conn, s, "ADD_COURSE", code)
    conn.commit()
    return cur.lastrowid


@require("manage_courses")
@_integrity
def assign_faculty(conn, s, course_id, faculty_id):
    conn.execute("UPDATE courses SET faculty_id = ? WHERE id = ?", (faculty_id, course_id))
    audit(conn, s, "ASSIGN_FACULTY", f"course {course_id} -> faculty {faculty_id}")
    conn.commit()


@require("view_courses")
def list_courses(conn, s, semester=None):
    sem = semester or "%"
    return _rows(conn.execute(
        "SELECT c.id, c.code, c.title, c.credits, d.code AS dept, "
        "COALESCE(f.name, 'TBA') AS instructor, c.capacity, "
        "(SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id AND e.semester LIKE ?) AS enrolled "
        "FROM courses c JOIN departments d ON d.id = c.dept_id "
        "LEFT JOIN faculty f ON f.id = c.faculty_id ORDER BY c.code", (sem,)))


@require("view_own_courses")
def my_courses(conn, s):
    return _rows(conn.execute(
        "SELECT course_id, code, title, enrolled, capacity, avg_marks, pass_rate "
        "FROM v_course_stats WHERE faculty_id = ? ORDER BY code", (s.ref_id,)))


@require("view_own_courses")
def course_roster(conn, s, course_id):
    _assert_teaches(conn, s, course_id)
    return _rows(conn.execute(
        "SELECT e.id AS enrollment_id, st.roll_no, st.name, e.semester, e.marks, e.letter "
        "FROM enrollments e JOIN students st ON st.id = e.student_id "
        "WHERE e.course_id = ? ORDER BY st.roll_no", (course_id,)))


def _assert_teaches(conn, s, course_id):
    row = conn.execute("SELECT faculty_id FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not row:
        raise ValueError("Course not found")
    if row["faculty_id"] != s.ref_id:
        raise PermissionDenied("You can only access courses you teach")


# ---------------------------------------------------------------- enrollments
@_integrity
def enroll(conn, s, course_id, semester, student_id=None):
    """Students enroll themselves; admins can enroll anyone."""
    if s.can("enroll_any"):
        if student_id is None:
            raise ValueError("student_id required")
        target = student_id
    elif s.can("self_enroll"):
        target = s.ref_id
    else:
        raise PermissionDenied(f"Role '{s.role}' cannot enroll students")
    cur = conn.execute("INSERT INTO enrollments(student_id, course_id, semester) VALUES (?,?,?)",
                       (target, course_id, semester))
    audit(conn, s, "ENROLL", f"student {target} course {course_id} {semester}")
    conn.commit()
    return cur.lastrowid


def drop(conn, s, enrollment_id):
    row = conn.execute("SELECT * FROM enrollments WHERE id = ?", (enrollment_id,)).fetchone()
    if not row:
        raise ValueError("Enrollment not found")
    if not s.can("enroll_any") and not (s.can("self_enroll") and row["student_id"] == s.ref_id):
        raise PermissionDenied("You cannot drop this enrollment")
    if row["marks"] is not None:
        raise ValueError("Cannot drop a course that has already been graded")
    conn.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
    audit(conn, s, "DROP", str(enrollment_id))
    conn.commit()


@require("grade_students")
def submit_marks(conn, s, enrollment_id, marks):
    if not 0 <= marks <= 100:
        raise ValueError("Marks must be between 0 and 100")
    row = conn.execute("SELECT course_id FROM enrollments WHERE id = ?", (enrollment_id,)).fetchone()
    if not row:
        raise ValueError("Enrollment not found")
    _assert_teaches(conn, s, row["course_id"])
    letter, points = letter_grade(marks)
    conn.execute("UPDATE enrollments SET marks=?, letter=?, grade_points=? WHERE id=?",
                 (marks, letter, points, enrollment_id))
    audit(conn, s, "GRADE", f"enrollment {enrollment_id}: {marks} ({letter})")
    conn.commit()
    return letter


@require("view_own_transcript")
def my_enrollments(conn, s):
    return transcript(conn, s.ref_id)


def transcript(conn, student_id):
    return _rows(conn.execute(
        "SELECT e.id AS enrollment_id, e.semester, c.code, c.title, c.credits, "
        "e.marks, e.letter, e.grade_points "
        "FROM enrollments e JOIN courses c ON c.id = e.course_id "
        "WHERE e.student_id = ? ORDER BY e.semester, c.code", (student_id,)))


@require("view_audit")
def audit_log(conn, s, limit=50):
    return _rows(conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)))
