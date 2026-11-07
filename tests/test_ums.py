import sqlite3
import unittest

from ums import auth, reports, services
from ums.auth import PermissionDenied, Session
from ums.db import connect, init_db


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_db(self.conn)
        auth.create_user(self.conn, "admin", "admin123", "admin")
        self.conn.commit()
        self.admin = auth.login(self.conn, "admin", "admin123")
        self.dept = services.add_department(self.conn, self.admin, "CS", "Computer Science")
        self.fac = services.add_faculty(self.conn, self.admin, "Dr. A", "a@u.edu", self.dept)
        self.fac2 = services.add_faculty(self.conn, self.admin, "Dr. B", "b@u.edu", self.dept)
        self.course = services.add_course(self.conn, self.admin, "CS101", "Intro", 3,
                                          self.dept, self.fac, capacity=2)
        self.course2 = services.add_course(self.conn, self.admin, "CS102", "Other", 3,
                                           self.dept, self.fac2)
        self.stu = [services.add_student(self.conn, self.admin, f"R{i}", f"S{i}",
                                         f"s{i}@u.edu", self.dept, 2024) for i in range(3)]
        self.faculty = auth.login(self.conn, "a", "faculty123")
        self.student = auth.login(self.conn, "r0", "student123")


class TestAuth(Base):
    def test_login_and_wrong_password(self):
        self.assertEqual(self.admin.role, "admin")
        self.assertIsNone(auth.login(self.conn, "admin", "wrong"))
        self.assertIsNone(auth.login(self.conn, "ghost", "x"))

    def test_passwords_are_hashed(self):
        stored = self.conn.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
        self.assertNotIn("admin123", stored)


class TestRBAC(Base):
    def test_student_cannot_manage(self):
        with self.assertRaises(PermissionDenied):
            services.add_student(self.conn, self.student, "X", "X", "x@u.edu", self.dept, 2024)
        with self.assertRaises(PermissionDenied):
            reports.top_students(self.conn, self.student)

    def test_faculty_cannot_grade_other_course(self):
        eid = services.enroll(self.conn, self.admin, self.course2, "F26", student_id=self.stu[0])
        with self.assertRaises(PermissionDenied):
            services.submit_marks(self.conn, self.faculty, eid, 90)

    def test_faculty_cannot_enroll(self):
        with self.assertRaises(PermissionDenied):
            services.enroll(self.conn, self.faculty, self.course, "F26", student_id=self.stu[0])


class TestEnrollmentAndGrades(Base):
    def test_capacity_trigger(self):
        services.enroll(self.conn, self.admin, self.course, "F26", student_id=self.stu[0])
        services.enroll(self.conn, self.admin, self.course, "F26", student_id=self.stu[1])
        with self.assertRaisesRegex(ValueError, "full"):
            services.enroll(self.conn, self.admin, self.course, "F26", student_id=self.stu[2])

    def test_duplicate_enrollment(self):
        services.enroll(self.conn, self.student, self.course, "F26")
        with self.assertRaises(ValueError):
            services.enroll(self.conn, self.student, self.course, "F26")

    def test_marks_validation_and_letter(self):
        eid = services.enroll(self.conn, self.student, self.course, "F26")
        with self.assertRaises(ValueError):
            services.submit_marks(self.conn, self.faculty, eid, 101)
        self.assertEqual(services.submit_marks(self.conn, self.faculty, eid, 86), "A")

    def test_gpa_is_credit_weighted(self):
        e1 = services.enroll(self.conn, self.student, self.course, "F26")      # 3 cr
        c3 = services.add_course(self.conn, self.admin, "CS200", "Big", 1, self.dept, self.fac)
        e2 = services.enroll(self.conn, self.student, c3, "F26")               # 1 cr
        services.submit_marks(self.conn, self.faculty, e1, 90)                 # 4.0
        services.submit_marks(self.conn, self.faculty, e2, 50)                 # 1.0
        self.assertEqual(services.my_profile(self.conn, self.student)["gpa"], 3.25)

    def test_cannot_drop_graded(self):
        eid = services.enroll(self.conn, self.student, self.course, "F26")
        services.submit_marks(self.conn, self.faculty, eid, 70)
        with self.assertRaises(ValueError):
            services.drop(self.conn, self.student, eid)

    def test_student_cannot_drop_others(self):
        eid = services.enroll(self.conn, self.admin, self.course, "F26", student_id=self.stu[1])
        with self.assertRaises(PermissionDenied):
            services.drop(self.conn, self.student, eid)


class TestIntegrity(Base):
    def test_delete_student_cascades(self):
        services.enroll(self.conn, self.student, self.course, "F26")
        services.delete_student(self.conn, self.admin, self.stu[0])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0], 0)
        self.assertIsNone(auth.login(self.conn, "r0", "student123"))

    def test_unique_roll_no(self):
        with self.assertRaises(ValueError):
            services.add_student(self.conn, self.admin, "R0", "Dup", "dup@u.edu", self.dept, 2024)

    def test_reports_and_audit(self):
        eid = services.enroll(self.conn, self.student, self.course, "F26")
        services.submit_marks(self.conn, self.faculty, eid, 40)
        self.assertEqual(len(reports.at_risk_students(self.conn, self.admin)), 1)
        self.assertEqual(reports.department_summary(self.conn, self.admin)[0]["students"], 3)
        self.assertTrue(services.audit_log(self.conn, self.admin))


if __name__ == "__main__":
    unittest.main()
