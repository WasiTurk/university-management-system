"""Authentication and role-based access control (RBAC)."""
import hashlib
import hmac
import os
from dataclasses import dataclass

PERMISSIONS = {
    "admin": {
        "manage_students", "manage_faculty", "manage_courses", "manage_departments",
        "enroll_any", "view_reports", "view_audit", "view_all_students", "view_courses",
    },
    "faculty": {"view_own_courses", "grade_students", "view_courses"},
    "student": {"view_own_profile", "self_enroll", "view_own_transcript", "view_courses"},
}


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class Session:
    user_id: int
    username: str
    role: str
    ref_id: "int | None"

    def can(self, permission: str) -> bool:
        return permission in PERMISSIONS.get(self.role, set())


def hash_password(password: str, salt: "bytes | None" = None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex(), digest.hex()


def create_user(conn, username, password, role, ref_id=None):
    if role not in PERMISSIONS:
        raise ValueError(f"Unknown role: {role}")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    salt, pw_hash = hash_password(password)
    conn.execute(
        "INSERT INTO users(username, salt, password_hash, role, ref_id) VALUES (?,?,?,?,?)",
        (username, salt, pw_hash, role, ref_id),
    )


def login(conn, username, password):
    """Return a Session on success, None on failure."""
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
    ).fetchone()
    if not row:
        hash_password(password)  # keep timing similar for unknown users
        return None
    _, attempt = hash_password(password, bytes.fromhex(row["salt"]))
    if not hmac.compare_digest(attempt, row["password_hash"]):
        return None
    return Session(row["id"], row["username"], row["role"], row["ref_id"])


def change_password(conn, session, old, new):
    if login(conn, session.username, old) is None:
        raise PermissionDenied("Current password is incorrect")
    if len(new) < 6:
        raise ValueError("Password must be at least 6 characters")
    salt, pw_hash = hash_password(new)
    conn.execute("UPDATE users SET salt=?, password_hash=? WHERE id=?",
                 (salt, pw_hash, session.user_id))
    conn.commit()
