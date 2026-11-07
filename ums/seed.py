"""Populate the database with realistic demo data."""
import random

from . import auth, services
from .db import connect, init_db

DEPARTMENTS = [("CS", "Computer Science"), ("EE", "Electrical Engineering"),
               ("BBA", "Business Administration"), ("MTH", "Mathematics")]
FIRST = ["Ali", "Ayesha", "Bilal", "Fatima", "Hamza", "Hira", "Imran", "Maryam", "Omar",
         "Sana", "Usman", "Zainab", "Asad", "Noor", "Saad", "Laiba", "Danish", "Iqra"]
LAST = ["Khan", "Ahmed", "Malik", "Raza", "Sheikh", "Butt", "Qureshi", "Iqbal", "Siddiqui", "Chaudhry"]
COURSES = {
    "CS": [("CS101", "Programming Fundamentals", 4), ("CS201", "Data Structures", 3),
           ("CS301", "Database Systems", 3), ("CS310", "Operating Systems", 3)],
    "EE": [("EE101", "Circuit Analysis", 4), ("EE210", "Digital Logic Design", 3)],
    "BBA": [("BA101", "Principles of Management", 3), ("BA220", "Financial Accounting", 3)],
    "MTH": [("MT101", "Calculus I", 3), ("MT202", "Linear Algebra", 3)],
}
SEMESTER = "Fall 2026"


def seed(conn, students=60, rng_seed=42):
    rng = random.Random(rng_seed)
    admin_user = conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone()
    if not admin_user:
        auth.create_user(conn, "admin", "admin123", "admin")
        conn.commit()
    s = auth.login(conn, "admin", "admin123")

    dept_ids = {code: services.add_department(conn, s, code, name) for code, name in DEPARTMENTS}

    fac_ids = {}
    for code, did in dept_ids.items():
        fac_ids[code] = []
        for i in range(2):
            name = f"Dr. {rng.choice(FIRST)} {rng.choice(LAST)}"
            email = f"{code.lower()}.prof{i + 1}@university.edu"
            desig = rng.choice(["Lecturer", "Assistant Professor", "Associate Professor", "Professor"])
            fac_ids[code].append(services.add_faculty(conn, s, name, email, did, desig))

    course_ids = []
    for code, items in COURSES.items():
        for i, (ccode, title, credits) in enumerate(items):
            course_ids.append(services.add_course(
                conn, s, ccode, title, credits, dept_ids[code],
                fac_ids[code][i % 2], capacity=rng.choice([25, 30, 40])))

    codes = list(dept_ids)
    for n in range(1, students + 1):
        dept = rng.choice(codes)
        year = rng.choice([2023, 2024, 2025, 2026])
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        roll = f"{year % 100}{dept}-{n:03d}"
        sid = services.add_student(conn, s, roll, name, f"{roll.lower()}@student.university.edu",
                                   dept_ids[dept], year)
        for cid in rng.sample(course_ids, k=rng.randint(3, 5)):
            try:
                services.enroll(conn, s, cid, SEMESTER, student_id=sid)
            except ValueError:
                pass  # course full

    # Grade ~85% of enrollments, acting as each course's own instructor
    rows = conn.execute("SELECT e.id, c.faculty_id FROM enrollments e "
                        "JOIN courses c ON c.id = e.course_id").fetchall()
    for r in rows:
        if rng.random() < 0.85:
            fsession = auth.Session(0, "seed", "faculty", r["faculty_id"])
            marks = max(20, min(100, round(rng.gauss(68, 15), 1)))
            services.submit_marks(conn, fsession, r["id"], marks)
    conn.commit()


def main(path=None, reset=True):
    from .db import DB_PATH
    target = path or DB_PATH
    if reset and target.exists():
        target.unlink()
    conn = connect(target)
    init_db(conn)
    seed(conn)
    print(f"Seeded {target}")
    print("Logins ->  admin / admin123   |  cs.prof1 / faculty123   |  22CS-001 style roll no (lowercase) / student123")
    conn.close()


if __name__ == "__main__":
    main()
