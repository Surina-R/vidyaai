import os
import sqlite3
from flask import g, current_app
from config import BASE_DIR

SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def get_db():
    """Open one database connection per request and reuse it."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row            # lets us use row["name"]
        g.db.execute("PRAGMA foreign_keys = ON")  # SQLite needs this to enforce relationships
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(db_path):
    """Create all tables (safe to run many times because of IF NOT EXISTS)."""
    conn = sqlite3.connect(db_path)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.close()