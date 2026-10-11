from flask import Blueprint, request, jsonify, session

from config import Config
from database import get_db
from auth import role_required, error
from quiz import check_topic_access
import ai_service

ai_bp = Blueprint("ai", __name__)
MAX_MESSAGE = 500


def clean_history(raw):
    """Never trust the browser: keep only the last 6 well-formed messages."""
    clean = []
    if not isinstance(raw, list):
        return clean
    for item in raw[-6:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        text = str(item.get("text", ""))[:1000]
        if role in ("user", "assistant") and text.strip():
            clean.append({"role": role, "text": text})
    return clean


def read_topic(db, raw, required):
    """Returns (topic_id, error_response). topic_id can be None if the topic is optional."""
    if raw in (None, ""):
        if required:
            return None, error("INVALID_INPUT", "Please choose a topic.")
        return None, None
    try:
        topic_id = int(raw)
    except (TypeError, ValueError):
        return None, error("INVALID_INPUT", "Invalid topic.")
    topic, problem = check_topic_access(db, session["user_id"], topic_id)
    if problem:
        return None, problem
    return topic_id, None


@ai_bp.get("/status")
@role_required("student")
def status():
    return jsonify(configured=ai_service.is_configured(), model=Config.GEMINI_MODEL)


@ai_bp.post("/tutor")
@role_required("student")
def tutor():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not 1 <= len(message) <= MAX_MESSAGE:
        return error("INVALID_INPUT", "Please type a question (up to 500 characters).")
    db = get_db()
    topic_id, problem = read_topic(db, data.get("topic_id"), required=False)
    if problem:
        return problem
    reply, source, note = ai_service.tutor_reply(
        db, session["user_id"], topic_id, message, clean_history(data.get("history")))
    return jsonify(reply=reply, source=source, note=note)


@ai_bp.post("/explain-mistakes")
@role_required("student")
def explain_mistakes():
    data = request.get_json(silent=True) or {}
    db = get_db()
    topic_id, problem = read_topic(db, data.get("topic_id"), required=True)
    if problem:
        return problem
    reply, source, note = ai_service.explain_mistakes(db, session["user_id"], topic_id)
    return jsonify(reply=reply, source=source, note=note)