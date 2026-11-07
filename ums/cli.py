"""Interactive, role-aware command line interface."""
import getpass
import sys

from . import auth, reports, services
from .auth import PermissionDenied
from .db import DB_PATH, connect, init_db

SEMESTER = "Fall 2026"


def table(rows, empty="(no records)"):
    if not rows:
        print(empty)
        return
    cols = list(rows[0].keys())
    cells = [[("" if r[c] is None else str(r[c])) for c in cols] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(cols)]
    line = "  ".join(c.upper().ljust(w) for c, w in zip(cols, widths))
    print(line)
    print("-" * len(line))
    for row in cells:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def ask(prompt, cast=str, default=None):
    while True:
        raw = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return cast(raw)
        except ValueError:
            print("  Invalid input, try again.")


def menu(title, options):
    print(f"\n=== {title} ===")
    for key, (label, _) in options.items():
        print(f"  {key}) {label}")
    return input("> ").strip()


def run_action(fn):
    try:
        fn()
    except (PermissionDenied, ValueError) as e:
        print(f"  ! {e}")


# ------------------------------------------------------------------ admin
def admin_menu(conn, s):
    def students():
        table(services.list_students(conn, s, ask("Search (blank = all)", default="") or None))

    def add_student():
        table(services.list_departments(conn))
        sid = services.add_student(conn, s, ask("Roll no"), ask("Name"), ask("Email"),
                                   ask("Dept id", int), ask("Enrollment year", int))
        print(f"  Student created (id {sid}); default password: student123")

    def del_student():
        services.delete_student(conn, s, ask("Student id", int))
        print("  Deleted.")

    def add_faculty():
        table(services.list_departments(conn))
        services.add_faculty(conn, s, ask("Name"), ask("Email"), ask("Dept id", int),
                             ask("Designation", default="Lecturer"))
        print("  Faculty created; default password: faculty123")

    def add_course():
        table(services.list_departments(conn))
        services.add_course(conn, s, ask("Code"), ask("Title"), ask("Credits", int),
                            ask("Dept id", int), ask("Faculty id (0 = none)", int, 0) or None,
                            ask("Capacity", int, 40))
        print("  Course created.")

    def enroll():
        services.enroll(conn, s, ask("Course id", int), ask("Semester", default=SEMESTER),
                        student_id=ask("Student id", int))
        print("  Enrolled.")

    opts = {
        "1": ("List/search students", students), "2": ("Add student", add_student),
        "3": ("Delete student", del_student),
        "4": ("List faculty", lambda: table(services.list_faculty(conn, s))),
        "5": ("Add faculty", add_faculty),
        "6": ("List courses", lambda: table(services.list_courses(conn, s))),
        "7": ("Add course", add_course), "8": ("Enroll a student", enroll),
        "9": ("Reports", lambda: reports_menu(conn, s)),
        "a": ("Audit log", lambda: table(services.audit_log(conn, s))),
        "0": ("Logout", None),
    }
    loop(opts, "Admin Menu")


def reports_menu(conn, s):
    def export(rows):
        if input("Export to CSV? (y/N): ").lower() == "y":
            path = ask("File name", default="report.csv")
            reports.export_csv(rows, path)
            print(f"  Saved {path}")

    def show(fn, *a):
        def inner():
            rows = fn(conn, s, *a)
            table(rows)
            if rows:
                export(rows)
        return inner

    opts = {
        "1": ("Top students by GPA", show(reports.top_students)),
        "2": ("At-risk students (GPA < 2.0)", show(reports.at_risk_students)),
        "3": ("Department summary", show(reports.department_summary)),
        "4": ("Course statistics", show(reports.course_stats)),
        "5": ("Grade distribution", show(reports.grade_distribution)),
        "6": ("Faculty workload", show(reports.faculty_workload)),
        "0": ("Back", None),
    }
    loop(opts, "Reports")


# ---------------------------------------------------------------- faculty
def faculty_menu(conn, s):
    def roster():
        cid = ask("Course id", int)
        table(services.course_roster(conn, s, cid))

    def grade():
        letter = services.submit_marks(conn, s, ask("Enrollment id", int), ask("Marks (0-100)", float))
        print(f"  Saved. Grade: {letter}")

    opts = {
        "1": ("My courses", lambda: table(services.my_courses(conn, s))),
        "2": ("Course roster", roster), "3": ("Submit marks", grade),
        "4": ("Change password", lambda: change_pw(conn, s)), "0": ("Logout", None),
    }
    loop(opts, "Faculty Menu")


# ---------------------------------------------------------------- student
def student_menu(conn, s):
    def profile():
        p = services.my_profile(conn, s)
        for k, v in p.items():
            print(f"  {k.replace('_', ' ').title():<16}: {v if v is not None else 'N/A'}")

    def enroll():
        table(services.list_courses(conn, s, SEMESTER))
        services.enroll(conn, s, ask("Course id", int), ask("Semester", default=SEMESTER))
        print("  Enrolled.")

    def drop():
        table(services.my_enrollments(conn, s))
        services.drop(conn, s, ask("Enrollment id", int))
        print("  Dropped.")

    opts = {
        "1": ("My profile & GPA", profile),
        "2": ("Browse courses", lambda: table(services.list_courses(conn, s, SEMESTER))),
        "3": ("Enroll in a course", enroll), "4": ("Drop a course", drop),
        "5": ("My transcript", lambda: table(services.my_enrollments(conn, s))),
        "6": ("Change password", lambda: change_pw(conn, s)), "0": ("Logout", None),
    }
    loop(opts, "Student Menu")


def change_pw(conn, s):
    auth.change_password(conn, s, getpass.getpass("Current password: "),
                         getpass.getpass("New password: "))
    print("  Password updated.")


def loop(opts, title):
    while True:
        choice = menu(title, opts)
        if choice == "0":
            return
        if choice in opts:
            run_action(opts[choice][1])
        else:
            print("  Unknown option.")


def main():
    if not DB_PATH.exists():
        print("No database found. Run:  python -m ums.seed   (or  python main.py --init)")
        sys.exit(1)
    conn = connect()
    init_db(conn)
    print("University Management System")
    for _ in range(3):
        s = auth.login(conn, input("Username: ").strip(), getpass.getpass("Password: "))
        if s:
            print(f"Welcome, {s.username} ({s.role})")
            {"admin": admin_menu, "faculty": faculty_menu, "student": student_menu}[s.role](conn, s)
            break
        print("Invalid credentials.")
    else:
        print("Too many failed attempts.")
    conn.close()
