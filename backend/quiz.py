import random
from flask import Blueprint, request, jsonify, session

from database import get_db
from auth import role_required, error
from analytics import (update_performance, generate_recommendations, active_recommendations,
                       recommended_difficulty)
from ai_service import add_questions_for_weak_topic

quiz_bp = Blueprint("quiz", __name__)

QUESTIONS_PER_QUIZ = 5
LETTERS = ("A", "B", "C", "D")


def check_topic_access(db, user_id, topic_id):
    """Returns (topic_row, None) if this student may use the topic, else (None, error_response)."""
    topic = db.execute(
        "SELECT t.id, t.name, t.grade_min, t.subject_id, t.prerequisite_id, s.name AS subject_name "
        "FROM topics t JOIN subjects s ON s.id = t.subject_id WHERE t.id = ?",
        (topic_id,),
    ).fetchone()
    if topic is None:
        return None, error("NOT_FOUND", "Topic not found.", 404)

    profile = db.execute("SELECT grade FROM student_profiles WHERE user_id = ?", (user_id,)).fetchone()
    enrolled = db.execute(
        "SELECT 1 FROM student_subjects WHERE user_id = ? AND subject_id = ?", (user_id, topic["subject_id"])
    ).fetchone()
    if profile is None or enrolled is None or topic["grade_min"] > profile["grade"]:
        return None, error("FORBIDDEN", "This topic is not available for you.", 403)
    return topic, None


def pick_questions(db, user_id, topic_id, difficulty, count):
    """Choose the questions for a quiz (this is the 'focus on weak areas' part).
    1. Questions closest to the wanted difficulty come first.
    2. Among those, questions the student got WRONG last time come first,
       then questions never seen, then questions already answered correctly.
    3. A little randomness breaks ties."""
    questions = db.execute("SELECT id, difficulty FROM questions WHERE topic_id = ?", (topic_id,)).fetchall()

    last_result = {}      # question id -> was the student's latest answer correct (1) or wrong (0)?
    for r in db.execute(
        "SELECT aa.question_id, aa.is_correct FROM attempt_answers aa "
        "JOIN quiz_attempts a ON a.id = aa.attempt_id "
        "WHERE a.user_id = ? AND a.topic_id = ? AND a.completed_at IS NOT NULL ORDER BY a.id, aa.id",
        (user_id, topic_id),
    ):
        last_result[r["question_id"]] = r["is_correct"]

    def sort_key(q):
        if q["id"] not in last_result:
            seen_rank = 1          # never seen
        elif last_result[q["id"]] == 0:
            seen_rank = 0          # got it wrong last time: practise again
        else:
            seen_rank = 2          # already correct
        return (abs(q["difficulty"] - difficulty), seen_rank, random.random())

    chosen = [q["id"] for q in sorted(questions, key=sort_key)[:count]]
    random.shuffle(chosen)
    return chosen


def get_own_attempt(db, attempt_id):
    """Load an attempt only if it belongs to the logged-in student."""
    return db.execute(
        "SELECT a.id, a.topic_id, a.difficulty, a.score, a.total_questions, a.completed_at, "
        "t.name AS topic_name FROM quiz_attempts a JOIN topics t ON t.id = a.topic_id "
        "WHERE a.id = ? AND a.user_id = ?",
        (attempt_id, session["user_id"]),
    ).fetchone()


def performance_for(db, user_id, topic_id):
    row = db.execute(
        "SELECT status, accuracy, attempts, current_difficulty FROM topic_performance "
        "WHERE user_id = ? AND topic_id = ?",
        (user_id, topic_id),
    ).fetchone()
    if row is None:
        return {"status": "new", "accuracy": 0, "attempts": 0, "recommended_difficulty": 1}
    return {"status": row["status"], "accuracy": row["accuracy"], "attempts": row["attempts"],
            "recommended_difficulty": row["current_difficulty"]}


@quiz_bp.get("/topic/<int:topic_id>")
@role_required("student")
def topic_detail(topic_id):
    db = get_db()
    topic, problem = check_topic_access(db, session["user_id"], topic_id)
    if problem:
        return problem

    counts = {"1": 0, "2": 0, "3": 0}
    for r in db.execute(
        "SELECT difficulty, COUNT(*) AS n FROM questions WHERE topic_id = ? GROUP BY difficulty", (topic_id,)
    ):
        counts[str(r["difficulty"])] = r["n"]

    prerequisite = None
    if topic["prerequisite_id"]:
        p = db.execute("SELECT id, name FROM topics WHERE id = ?", (topic["prerequisite_id"],)).fetchone()
        prerequisite = dict(p) if p else None

    attempts = db.execute(
        "SELECT id, difficulty, score, total_questions, completed_at FROM quiz_attempts "
        "WHERE user_id = ? AND topic_id = ? AND completed_at IS NOT NULL ORDER BY id DESC LIMIT 5",
        (session["user_id"], topic_id),
    ).fetchall()

    return jsonify(
        topic={"id": topic["id"], "name": topic["name"], "subject_name": topic["subject_name"]},
        prerequisite=prerequisite,
        question_counts=counts,
        questions_per_quiz=QUESTIONS_PER_QUIZ,
        attempts=[dict(a) for a in attempts],
        performance=performance_for(db, session["user_id"], topic_id),
    )


@quiz_bp.post("/start")
@role_required("student")
def start_quiz():
    data = request.get_json(silent=True) or {}
    try:
        topic_id = int(data.get("topic_id"))
        raw = data.get("difficulty", "auto")
        difficulty = None if raw == "auto" else int(raw)      # "auto" = let the system choose
    except (TypeError, ValueError):
        return error("INVALID_INPUT", "Invalid topic or difficulty.")
    if difficulty is not None and difficulty not in (1, 2, 3):
        return error("INVALID_INPUT", "Difficulty must be 1, 2, 3 or auto.")

    db = get_db()
    topic, problem = check_topic_access(db, session["user_id"], topic_id)
    if problem:
        return problem

    if difficulty is None:
        difficulty = recommended_difficulty(db, session["user_id"], topic_id)

    # AI step of the loop: if the topic is weak, create fresh questions aimed at the student's mistakes
    ai_added = add_questions_for_weak_topic(db, session["user_id"], topic_id, difficulty)

    question_ids = pick_questions(db, session["user_id"], topic_id, difficulty, QUESTIONS_PER_QUIZ)
    if not question_ids:
        return error("NO_QUESTIONS", "There are no questions for this topic yet.", 404)

    cur = db.execute(
        "INSERT INTO quiz_attempts (user_id, topic_id, difficulty, total_questions) VALUES (?, ?, ?, ?)",
        (session["user_id"], topic_id, difficulty, len(question_ids)),
    )
    attempt_id = cur.lastrowid
    # One empty answer row per question. It is filled in when the student submits.
    db.executemany(
        "INSERT INTO attempt_answers (attempt_id, question_id) VALUES (?, ?)",
        [(attempt_id, qid) for qid in question_ids],
    )
    db.commit()
    return jsonify(attempt_id=attempt_id, ai_added=ai_added), 201


@quiz_bp.get("/history")
@role_required("student")
def history():
    rows = get_db().execute(
        "SELECT a.id, a.score, a.total_questions, a.difficulty, a.completed_at, t.name AS topic_name "
        "FROM quiz_attempts a JOIN topics t ON t.id = a.topic_id "
        "WHERE a.user_id = ? AND a.completed_at IS NOT NULL ORDER BY a.id DESC LIMIT 10",
        (session["user_id"],),
    ).fetchall()
    return jsonify(attempts=[dict(r) for r in rows])


@quiz_bp.get("/<int:attempt_id>")
@role_required("student")
def get_quiz(attempt_id):
    """Returns the questions of a quiz. The correct answers are NOT sent."""
    db = get_db()
    attempt = get_own_attempt(db, attempt_id)
    if attempt is None:
        return error("NOT_FOUND", "Quiz not found.", 404)
    if attempt["completed_at"]:
        return jsonify(completed=True, attempt_id=attempt_id)

    rows = db.execute(
        "SELECT q.id, q.question_text, q.option_a, q.option_b, q.option_c, q.option_d "
        "FROM attempt_answers aa JOIN questions q ON q.id = aa.question_id "
        "WHERE aa.attempt_id = ? ORDER BY aa.id",
        (attempt_id,),
    ).fetchall()
    questions = [{
        "id": r["id"],
        "text": r["question_text"],
        "options": {"A": r["option_a"], "B": r["option_b"], "C": r["option_c"], "D": r["option_d"]},
    } for r in rows]
    return jsonify(
        completed=False, attempt_id=attempt_id, topic_name=attempt["topic_name"],
        difficulty=attempt["difficulty"], questions=questions,
    )


@quiz_bp.post("/<int:attempt_id>/submit")
@role_required("student")
def submit_quiz(attempt_id):
    """The SERVER checks the answers. Then it runs the feedback loop:
    update performance -> detect weak topics -> adapt difficulty -> new recommendations."""
    db = get_db()
    attempt = get_own_attempt(db, attempt_id)
    if attempt is None:
        return error("NOT_FOUND", "Quiz not found.", 404)
    if attempt["completed_at"]:
        return error("ALREADY_SUBMITTED", "This quiz was already submitted.", 409)

    data = request.get_json(silent=True) or {}
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return error("INVALID_INPUT", "Answers must be an object.")

    rows = db.execute(
        "SELECT aa.id, aa.question_id, q.correct_option FROM attempt_answers aa "
        "JOIN questions q ON q.id = aa.question_id WHERE aa.attempt_id = ?",
        (attempt_id,),
    ).fetchall()

    score = 0
    for r in rows:
        selected = answers.get(str(r["question_id"]))
        if selected not in LETTERS:          # missing or invalid means unanswered
            selected = None
        is_correct = 1 if selected == r["correct_option"] else 0
        score += is_correct
        db.execute(
            "UPDATE attempt_answers SET selected_option = ?, is_correct = ?, answered_at = datetime('now') "
            "WHERE id = ?",
            (selected, is_correct, r["id"]),
        )
    db.execute(
        "UPDATE quiz_attempts SET score = ?, completed_at = datetime('now') WHERE id = ?", (score, attempt_id)
    )

    # ---- The feedback loop (all saved together in one commit) ----
    update_performance(db, session["user_id"], attempt["topic_id"], attempt_id)
    generate_recommendations(db, session["user_id"])
    db.commit()
    return jsonify(attempt_id=attempt_id, score=score, total=len(rows))


@quiz_bp.get("/<int:attempt_id>/result")
@role_required("student")
def quiz_result(attempt_id):
    db = get_db()
    attempt = get_own_attempt(db, attempt_id)
    if attempt is None:
        return error("NOT_FOUND", "Quiz not found.", 404)
    if not attempt["completed_at"]:
        return error("NOT_FINISHED", "Finish the quiz first.", 409)

    rows = db.execute(
        "SELECT q.question_text, q.option_a, q.option_b, q.option_c, q.option_d, q.correct_option, "
        "q.explanation, aa.selected_option, aa.is_correct "
        "FROM attempt_answers aa JOIN questions q ON q.id = aa.question_id "
        "WHERE aa.attempt_id = ? ORDER BY aa.id",
        (attempt_id,),
    ).fetchall()
    answers = [{
        "text": r["question_text"],
        "options": {"A": r["option_a"], "B": r["option_b"], "C": r["option_c"], "D": r["option_d"]},
        "selected": r["selected_option"],
        "correct": r["correct_option"],
        "is_correct": bool(r["is_correct"]),
        "explanation": r["explanation"],
    } for r in rows]

    # The quiz before this one on the same topic (used to show improvement)
    prev = db.execute(
        "SELECT score, total_questions FROM quiz_attempts "
        "WHERE user_id = ? AND topic_id = ? AND completed_at IS NOT NULL AND id < ? ORDER BY id DESC LIMIT 1",
        (session["user_id"], attempt["topic_id"], attempt_id),
    ).fetchone()
    previous = {"score": prev["score"], "total": prev["total_questions"]} if prev else None

    return jsonify(
        attempt_id=attempt_id, topic_id=attempt["topic_id"], topic_name=attempt["topic_name"],
        difficulty=attempt["difficulty"], score=attempt["score"], total=attempt["total_questions"],
        answers=answers, previous=previous,
        performance=performance_for(db, session["user_id"], attempt["topic_id"]),
        recommendations=active_recommendations(db, session["user_id"]),
    )