import re
import sqlite3
import time
from functools import wraps

from flask import Blueprint, request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db
from config import GRADES

auth_bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def error(code, message, status=400):
    """Every error has a machine-readable 'code' and a readable message."""
    return jsonify(code=code, error=message), status


# ---------- Access-control helpers (used by other files later) ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return error("NOT_LOGGED_IN", "Please log in first.", 401)
        return f(*args, **kwargs)
    return wrapper


def role_required(role):
    """Allow only users with the given role ('student' or 'teacher')."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return error("NOT_LOGGED_IN", "Please log in first.", 401)
            if session.get("role") != role:
                return error("FORBIDDEN", "You do not have access to this.", 403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ---------- Simple login rate limiting (kept in memory) ----------
FAILED_LOGINS = {}
MAX_FAILS = 5
WINDOW_SECONDS = 300


def too_many_failures(key):
    now = time.time()
    FAILED_LOGINS[key] = [t for t in FAILED_LOGINS.get(key, []) if now - t < WINDOW_SECONDS]
    return len(FAILED_LOGINS[key]) >= MAX_FAILS


def user_payload(db, user_id):
    """User + profile + subjects sent to the frontend. Never includes the password hash."""
    user = db.execute("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return None
    payload = {"user": dict(user), "profile": None, "subject_ids": []}
    if user["role"] == "student":
        profile = db.execute(
            "SELECT grade, school, level FROM student_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        payload["profile"] = dict(profile) if profile else None
        rows = db.execute("SELECT subject_id FROM student_subjects WHERE user_id = ?", (user_id,)).fetchall()
        payload["subject_ids"] = [r["subject_id"] for r in rows]
    return payload


# ---------- Endpoints ----------
@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    school = str(data.get("school") or "").strip()[:100]

    # --- Input validation (never trust data from the browser) ---
    if not 2 <= len(name) <= 60:
        return error("INVALID_NAME", "Name must be 2 to 60 characters.")
    if not EMAIL_RE.match(email) or len(email) > 120:
        return error("INVALID_EMAIL", "Please enter a valid email address.")
    if not (8 <= len(password) <= 100 and re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        return error("WEAK_PASSWORD", "Password must be 8+ characters with at least one letter and one number.")
    try:
        grade = int(data.get("grade"))
    except (TypeError, ValueError):
        return error("INVALID_GRADE", "Please choose a valid class.")
    if grade not in GRADES:
        return error("INVALID_GRADE", "Please choose a valid class.")

    db = get_db()
    try:
        subject_ids = {int(s) for s in (data.get("subjects") or [])}
    except (TypeError, ValueError):
        return error("INVALID_SUBJECTS", "Please choose at least one subject.")
    valid_ids = {r["id"] for r in db.execute("SELECT id FROM subjects").fetchall()}
    if not subject_ids or not subject_ids.issubset(valid_ids):
        return error("INVALID_SUBJECTS", "Please choose at least one subject.")

    # --- Save to the database (all inserts succeed together or none do) ---
    try:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'student')",
            (name, email, generate_password_hash(password, method="pbkdf2:sha256")),
        )
        user_id = cur.lastrowid
        db.execute(
            "INSERT INTO student_profiles (user_id, grade, school) VALUES (?, ?, ?)",
            (user_id, grade, school),
        )
        db.executemany(
            "INSERT INTO student_subjects (user_id, subject_id) VALUES (?, ?)",
            [(user_id, s) for s in subject_ids],
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return error("EMAIL_EXISTS", "This email is already registered.", 409)

    session.clear()
    session["user_id"] = user_id
    session["role"] = "student"
    return jsonify(user_payload(db, user_id)), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    key = (request.remote_addr or "?") + "|" + email
    if too_many_failures(key):
        return error("TOO_MANY_ATTEMPTS", "Too many failed attempts. Please wait 5 minutes.", 429)

    db = get_db()
    user = db.execute("SELECT id, password_hash, role FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        FAILED_LOGINS.setdefault(key, []).append(time.time())
        # Same message for "no such email" and "wrong password" so attackers learn nothing
        return error("BAD_CREDENTIALS", "Incorrect email or password.", 401)

    FAILED_LOGINS.pop(key, None)
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    return jsonify(user_payload(db, user["id"]))


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@auth_bp.get("/me")
@login_required
def me():
    payload = user_payload(get_db(), session["user_id"])
    if payload is None:  # account was deleted
        session.clear()
        return error("NOT_LOGGED_IN", "Please log in first.", 401)
    return jsonify(payload)