from flask import Blueprint, jsonify, session

from database import get_db
from auth import role_required

analytics_bp = Blueprint("analytics", __name__)

# ---- The rules of the system. Change the numbers here to tune it. ----
WEAK_BELOW = 50          # recent accuracy below 50%   -> "weak"
STRONG_FROM = 80         # recent accuracy 80% or more -> "strong"
RECENT_ANSWERS = 10      # "recent accuracy" = the last 10 answers on a topic
LEVEL_UP_AT = 80         # a quiz score of 80%+ raises the difficulty
LEVEL_DOWN_BELOW = 50    # a quiz score below 50% lowers the difficulty
LEVEL_NAMES = {1: "Easy", 2: "Medium", 3: "Hard"}


def status_from_accuracy(accuracy):
    if accuracy < WEAK_BELOW:
        return "weak"
    if accuracy >= STRONG_FROM:
        return "strong"
    return "average"


# ======================= PERFORMANCE TRACKING =======================
def update_performance(db, user_id, topic_id, attempt_id):
    """Recalculate one student's performance on one topic from the saved answers.
    Called every time a quiz is submitted. Does not commit; the caller commits."""
    attempts = db.execute(
        "SELECT COUNT(*) FROM quiz_attempts WHERE user_id = ? AND topic_id = ? AND completed_at IS NOT NULL",
        (user_id, topic_id),
    ).fetchone()[0]

    # Every answer the student ever gave on this topic, oldest first (1 = correct, 0 = wrong)
    flags = [r["is_correct"] for r in db.execute(
        "SELECT aa.is_correct FROM attempt_answers aa JOIN quiz_attempts a ON a.id = aa.attempt_id "
        "WHERE a.user_id = ? AND a.topic_id = ? AND a.completed_at IS NOT NULL ORDER BY a.id, aa.id",
        (user_id, topic_id),
    )]
    answered = len(flags)
    correct = sum(flags)
    recent = flags[-RECENT_ANSWERS:]
    accuracy = round(100.0 * sum(recent) / len(recent), 1) if recent else 0
    status = status_from_accuracy(accuracy) if recent else "new"

    # Adaptive difficulty: move one step up or down based on THIS quiz's score
    row = db.execute(
        "SELECT current_difficulty FROM topic_performance WHERE user_id = ? AND topic_id = ?",
        (user_id, topic_id),
    ).fetchone()
    difficulty = row["current_difficulty"] if row else 1
    attempt = db.execute(
        "SELECT score, total_questions FROM quiz_attempts WHERE id = ?", (attempt_id,)
    ).fetchone()
    if attempt and attempt["total_questions"]:
        percent = 100.0 * attempt["score"] / attempt["total_questions"]
        if percent >= LEVEL_UP_AT:
            difficulty = min(3, difficulty + 1)
        elif percent < LEVEL_DOWN_BELOW:
            difficulty = max(1, difficulty - 1)

    db.execute(
        "INSERT OR REPLACE INTO topic_performance "
        "(user_id, topic_id, attempts, questions_answered, correct_answers, accuracy, "
        " current_difficulty, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (user_id, topic_id, attempts, answered, correct, accuracy, difficulty, status),
    )


def recommended_difficulty(db, user_id, topic_id):
    row = db.execute(
        "SELECT current_difficulty FROM topic_performance WHERE user_id = ? AND topic_id = ?",
        (user_id, topic_id),
    ).fetchone()
    return row["current_difficulty"] if row else 1


def student_topics(db, user_id):
    """Every topic this student can study, with performance (topics never attempted get status 'new')."""
    return db.execute(
        "SELECT t.id, t.name, t.prerequisite_id, s.name AS subject_name, "
        "  COALESCE(p.status, 'new') AS status, COALESCE(p.accuracy, 0) AS accuracy, "
        "  COALESCE(p.attempts, 0) AS attempts, COALESCE(p.current_difficulty, 1) AS difficulty, "
        "  COALESCE(p.questions_answered, 0) AS questions_answered, "
        "  COALESCE(p.correct_answers, 0) AS correct_answers "
        "FROM topics t "
        "JOIN subjects s ON s.id = t.subject_id "
        "JOIN student_subjects ss ON ss.subject_id = t.subject_id AND ss.user_id = ? "
        "JOIN student_profiles sp ON sp.user_id = ? AND t.grade_min <= sp.grade "
        "LEFT JOIN topic_performance p ON p.topic_id = t.id AND p.user_id = ? "
        "ORDER BY t.sort_order",
        (user_id, user_id, user_id),
    ).fetchall()


# ======================= RECOMMENDATION ENGINE =======================
def generate_recommendations(db, user_id):
    """Rule-based recommendations. Old ones are kept as history but marked inactive.
    Does not commit; the caller commits."""
    topics = [dict(r) for r in student_topics(db, user_id)]
    by_id = {t["id"]: t for t in topics}
    recs = []                       # (topic_id, action_type, message)
    revised = set()

    # Rule 1: weak topics come first (worst first, at most 2)
    weak = sorted([t for t in topics if t["status"] == "weak"], key=lambda t: t["accuracy"])
    for t in weak[:2]:
        pre = by_id.get(t["prerequisite_id"])
        if pre and pre["status"] == "weak" and pre["id"] not in revised:
            revised.add(pre["id"])
            recs.append((pre["id"], "revise",
                         "Revise " + pre["name"] + " first. It is the base for " + t["name"] + ", which you also find difficult."))
        if t["id"] not in revised:
            revised.add(t["id"])
            recs.append((t["id"], "revise",
                         "Revise " + t["name"] + ": your recent accuracy is " + str(round(t["accuracy"])) +
                         "%. Read the explanations from your last quiz."))
        recs.append((t["id"], "quiz",
                     "Then take a " + LEVEL_NAMES[t["difficulty"]] + " quiz on " + t["name"] + " to check your improvement."))

    # Rule 2: suggest new topics, but only if the prerequisite is Average or Strong
    learn_count = 0
    for t in topics:
        if t["status"] != "new" or learn_count >= 2:
            continue
        pre = by_id.get(t["prerequisite_id"])
        if pre is None or pre["status"] in ("average", "strong"):
            recs.append((t["id"], "learn", "Start learning " + t["name"] + " (" + t["subject_name"] + ")."))
            learn_count += 1

    # Rule 3: push one "average" topic towards "strong"
    average = sorted([t for t in topics if t["status"] == "average"], key=lambda t: t["accuracy"])
    if average:
        t = average[0]
        recs.append((t["id"], "quiz",
                     "Practise " + t["name"] + " at " + LEVEL_NAMES[t["difficulty"]] + " level to move from average to strong."))

    db.execute("UPDATE recommendations SET is_active = 0 WHERE user_id = ? AND is_active = 1", (user_id,))
    db.executemany(
        "INSERT INTO recommendations (user_id, topic_id, action_type, message) VALUES (?, ?, ?, ?)",
        [(user_id, tid, action, message) for tid, action, message in recs[:6]],
    )


def active_recommendations(db, user_id):
    rows = db.execute(
        "SELECT r.id, r.topic_id, r.action_type, r.message, t.name AS topic_name "
        "FROM recommendations r JOIN topics t ON t.id = r.topic_id "
        "WHERE r.user_id = ? AND r.is_active = 1 ORDER BY r.id",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def ensure_recommendations(db, user_id):
    """A brand-new student has none yet, so create the first ones."""
    recs = active_recommendations(db, user_id)
    if not recs:
        generate_recommendations(db, user_id)
        db.commit()
        recs = active_recommendations(db, user_id)
    return recs


# ======================= API ENDPOINTS =======================
@analytics_bp.get("/dashboard")
@role_required("student")
def dashboard():
    db = get_db()
    uid = session["user_id"]
    topics = [dict(r) for r in student_topics(db, uid)]

    totals = db.execute(
        "SELECT COUNT(*) AS quizzes, COALESCE(SUM(score), 0) AS correct, COALESCE(SUM(total_questions), 0) AS total "
        "FROM quiz_attempts WHERE user_id = ? AND completed_at IS NOT NULL",
        (uid,),
    ).fetchone()
    accuracy = round(100 * totals["correct"] / totals["total"]) if totals["total"] else 0
    strong = [t for t in topics if t["status"] == "strong"]

    return jsonify(
        stats={
            "quizzes": totals["quizzes"],
            "questions": totals["total"],
            "accuracy": accuracy,
            "topics_total": len(topics),
            "topics_strong": len(strong),
            "mastery_percent": round(100 * len(strong) / len(topics)) if topics else 0,
        },
        weak=[t for t in topics if t["status"] == "weak"],
        average=[t for t in topics if t["status"] == "average"],
        strong=strong,
        recommendations=ensure_recommendations(db, uid),
    )


@analytics_bp.get("/progress")
@role_required("student")
def progress():
    db = get_db()
    uid = session["user_id"]
    topics = [dict(r) for r in student_topics(db, uid)]

    attempts = db.execute(
        "SELECT a.id, a.topic_id, t.name AS topic_name, a.score, a.total_questions, a.difficulty, a.completed_at "
        "FROM quiz_attempts a JOIN topics t ON t.id = a.topic_id "
        "WHERE a.user_id = ? AND a.completed_at IS NOT NULL ORDER BY a.id",
        (uid,),
    ).fetchall()

    timeline = []
    per_topic = {}
    for a in attempts:
        percent = round(100 * a["score"] / a["total_questions"]) if a["total_questions"] else 0
        item = {"id": a["id"], "topic_name": a["topic_name"], "difficulty": a["difficulty"],
                "percent": percent, "completed_at": a["completed_at"]}
        timeline.append(item)
        per_topic.setdefault(a["topic_id"], []).append(item)

    # Improvement = first quiz score vs latest quiz score on the same topic
    improvement = []
    for topic_id, items in per_topic.items():
        if len(items) >= 2:
            improvement.append({
                "topic_id": topic_id, "topic_name": items[0]["topic_name"],
                "first": items[0]["percent"], "latest": items[-1]["percent"],
                "change": items[-1]["percent"] - items[0]["percent"], "attempts": len(items),
            })

    return jsonify(topics=topics, timeline=timeline[-15:], improvement=improvement)


@analytics_bp.get("/recommendations")
@role_required("student")
def recommendations():
    db = get_db()
    return jsonify(recommendations=ensure_recommendations(db, session["user_id"]))
