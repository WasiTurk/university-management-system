"""Admin reporting. All queries read from SQL views / aggregates."""
import csv

from .services import _rows, require


@require("view_reports")
def top_students(conn, s, limit=10):
    return _rows(conn.execute(
        "SELECT g.roll_no, g.name, d.code AS dept, g.credits_earned, g.gpa "
        "FROM v_student_gpa g JOIN departments d ON d.id = g.dept_id "
        "WHERE g.gpa IS NOT NULL ORDER BY g.gpa DESC, g.credits_earned DESC LIMIT ?", (limit,)))


@require("view_reports")
def at_risk_students(conn, s, threshold=2.0):
    return _rows(conn.execute(
        "SELECT g.roll_no, g.name, d.code AS dept, g.gpa "
        "FROM v_student_gpa g JOIN departments d ON d.id = g.dept_id "
        "WHERE g.gpa < ? ORDER BY g.gpa", (threshold,)))


@require("view_reports")
def department_summary(conn, s):
    return _rows(conn.execute("""
        SELECT d.code, d.name,
               (SELECT COUNT(*) FROM students  WHERE dept_id = d.id) AS students,
               (SELECT COUNT(*) FROM faculty   WHERE dept_id = d.id) AS faculty,
               (SELECT COUNT(*) FROM courses   WHERE dept_id = d.id) AS courses,
               (SELECT ROUND(AVG(gpa), 2) FROM v_student_gpa WHERE dept_id = d.id) AS avg_gpa
        FROM departments d ORDER BY d.name"""))


@require("view_reports")
def course_stats(conn, s):
    return _rows(conn.execute(
        "SELECT code, title, enrolled, capacity, avg_marks, pass_rate "
        "FROM v_course_stats ORDER BY code"))


@require("view_reports")
def grade_distribution(conn, s, course_id=None):
    sql = "SELECT letter, COUNT(*) AS count FROM enrollments WHERE letter IS NOT NULL"
    params = []
    if course_id:
        sql += " AND course_id = ?"
        params.append(course_id)
    sql += " GROUP BY letter ORDER BY MIN(grade_points) DESC"
    return _rows(conn.execute(sql, params))


@require("view_reports")
def faculty_workload(conn, s):
    return _rows(conn.execute("""
        SELECT f.name, f.designation, COUNT(DISTINCT c.id) AS courses,
               COALESCE(SUM(c.credits), 0) AS credit_hours,
               (SELECT COUNT(*) FROM enrollments e JOIN courses c2 ON c2.id = e.course_id
                WHERE c2.faculty_id = f.id) AS total_students
        FROM faculty f LEFT JOIN courses c ON c.faculty_id = f.id
        GROUP BY f.id ORDER BY credit_hours DESC"""))


def export_csv(rows, path):
    if not rows:
        raise ValueError("Nothing to export")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return path
