"""Recalculates performance and recommendations from quizzes that are already saved.
Run once after installing Phase 3:  python recalc.py"""
import sqlite3

from config import Config
from analytics import update_performance, generate_recommendations

conn = sqlite3.connect(Config.DATABASE_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")

pairs = conn.execute(
    "SELECT user_id, topic_id, MAX(id) AS last_id FROM quiz_attempts "
    "WHERE completed_at IS NOT NULL GROUP BY user_id, topic_id"
).fetchall()
for p in pairs:
    update_performance(conn, p["user_id"], p["topic_id"], p["last_id"])

for u in conn.execute("SELECT id FROM users WHERE role = 'student'").fetchall():
    generate_recommendations(conn, u["id"])

conn.commit()
conn.close()
print("Done. Updated", len(pairs), "student-topic records.")