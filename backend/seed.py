"""Creates the database and fills it with subjects, topics, questions and demo accounts.
Run:  python seed.py            (safe to run again; it never creates duplicates)
      python seed.py --reset    (deletes the old database first)
"""
import os
import sys
import sqlite3
from werkzeug.security import generate_password_hash

from config import Config
from database import init_db
from questions_data import QUESTIONS

SUBJECTS = [("math", "Mathematics"), ("science", "Science")]

# (subject_code, topic_code, name, minimum_grade, prerequisite_topic_code)
TOPICS = [
    ("math", "addition_subtraction", "Addition & Subtraction", 6, None),
    ("math", "multiplication_division", "Multiplication & Division", 6, "addition_subtraction"),
    ("math", "fractions", "Fractions", 6, "multiplication_division"),
    ("math", "equivalent_fractions", "Equivalent Fractions", 6, "fractions"),
    ("math", "decimals", "Decimals", 6, "equivalent_fractions"),
    ("math", "percentages", "Percentages", 7, "decimals"),
    ("science", "parts_of_plant", "Parts of a Plant", 6, None),
    ("science", "photosynthesis", "Photosynthesis", 6, "parts_of_plant"),
    ("science", "states_of_matter", "States of Matter", 6, None),
    ("science", "force_and_motion", "Force and Motion", 7, None),
    ("science", "electricity_basics", "Basic Electricity", 7, None),
]


def add_user(conn, name, email, password, role):
    conn.execute(
        "INSERT OR IGNORE INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash(password, method="pbkdf2:sha256"), role),
    )
    return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]


def main():
    if "--reset" in sys.argv and os.path.exists(Config.DATABASE_PATH):
        os.remove(Config.DATABASE_PATH)
        print("Old database deleted.")

    init_db(Config.DATABASE_PATH)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    for code, name in SUBJECTS:
        conn.execute("INSERT OR IGNORE INTO subjects (code, name) VALUES (?, ?)", (code, name))

    for order, (subj, code, name, grade_min, prereq) in enumerate(TOPICS, start=1):
        subject_id = conn.execute("SELECT id FROM subjects WHERE code = ?", (subj,)).fetchone()[0]
        prereq_id = None
        if prereq:  # prerequisites are listed earlier in TOPICS, so they already exist
            prereq_id = conn.execute("SELECT id FROM topics WHERE code = ?", (prereq,)).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO topics (subject_id, code, name, grade_min, prerequisite_id, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (subject_id, code, name, grade_min, prereq_id, order),
        )

    # Question bank: skip any question that is already stored
    added = 0
    for topic_code, difficulty, text, options, correct, explanation in QUESTIONS:
        topic_id = conn.execute("SELECT id FROM topics WHERE code = ?", (topic_code,)).fetchone()[0]
        exists = conn.execute(
            "SELECT 1 FROM questions WHERE topic_id = ? AND question_text = ?", (topic_id, text)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO questions (topic_id, difficulty, language, question_text, option_a, option_b, "
            "option_c, option_d, correct_option, explanation, source) "
            "VALUES (?, ?, 'en', ?, ?, ?, ?, ?, ?, ?, 'bank')",
            (topic_id, difficulty, text, options[0], options[1], options[2], options[3], correct, explanation),
        )
        added += 1

    # Demo accounts
    add_user(conn, "Demo Teacher", "teacher@vidyaai.test", "Teacher@123", "teacher")
    sid = add_user(conn, "Demo Student", "student@vidyaai.test", "Student@123", "student")
    conn.execute(
        "INSERT OR IGNORE INTO student_profiles (user_id, grade, school) VALUES (?, 7, ?)",
        (sid, "Government High School (Demo)"),
    )
    for (subject_id,) in conn.execute("SELECT id FROM subjects").fetchall():
        conn.execute("INSERT OR IGNORE INTO student_subjects (user_id, subject_id) VALUES (?, ?)", (sid, subject_id))

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    conn.close()
    print("Database ready:", Config.DATABASE_PATH)
    print("Questions added now:", added, "| total in database:", total)
    print("Demo student: student@vidyaai.test / Student@123")
    print("Demo teacher: teacher@vidyaai.test / Teacher@123")


if __name__ == "__main__":
    main()