from flask import Blueprint, jsonify
from database import get_db
from config import GRADES

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.get("/meta")
def meta():
    """One request returns grades, subjects and topics."""
    db = get_db()
    subjects = []
    for s in db.execute("SELECT id, code, name FROM subjects ORDER BY id").fetchall():
        topics = db.execute(
            "SELECT id, code, name, grade_min, prerequisite_id FROM topics "
            "WHERE subject_id = ? ORDER BY sort_order, id",
            (s["id"],),
        ).fetchall()
        subjects.append({
            "id": s["id"], "code": s["code"], "name": s["name"],
            "topics": [dict(t) for t in topics],
        })
    return jsonify(grades=GRADES, subjects=subjects)