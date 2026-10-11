"""All AI logic: prompts built from the student's data, calls to Gemini, validation, offline fallback."""
import json
import re
import time

import requests

from config import Config
from lessons_data import LESSONS

LETTERS = ("A", "B", "C", "D")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 20            # never make the student wait longer than this
MAX_AI_CALLS_PER_HOUR = 30      # per student, protects the free quota
NEW_QUESTIONS_PER_QUIZ = 3      # AI questions created when a weak topic quiz starts
MAX_AI_QUESTIONS_PER_TOPIC = 30


class AIUnavailable(Exception):
    """Raised when the AI cannot be used. The callers then use the offline fallback."""


def is_configured():
    return bool(Config.GEMINI_API_KEY)


# ---------- Simple per-student limit (kept in memory) ----------
_calls = {}


def allow_call(user_id):
    now = time.time()
    recent = [t for t in _calls.get(user_id, []) if now - t < 3600]
    if len(recent) >= MAX_AI_CALLS_PER_HOUR:
        _calls[user_id] = recent
        return False
    recent.append(now)
    _calls[user_id] = recent
    return True


# ---------- The one function that talks to Gemini ----------
def call_gemini(system_text, contents, max_tokens=1024, json_mode=False):
    if not is_configured():
        raise AIUnavailable("no API key")
    body = {
        "system_instruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": max_tokens},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    try:
        resp = requests.post(
            API_URL.format(model=Config.GEMINI_MODEL),
            headers={"x-goog-api-key": Config.GEMINI_API_KEY, "Content-Type": "application/json"},
            json=body, timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        print("[AI] network problem:", type(e).__name__)
        raise AIUnavailable("network") from e
    if resp.status_code != 200:
        # Printed in the terminal so you can debug (400/403 = bad key, 404 = bad model name, 429 = limit reached)
        print("[AI] HTTP", resp.status_code, resp.text[:200])
        raise AIUnavailable("HTTP %s" % resp.status_code)
    try:
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError, ValueError) as e:
        print("[AI] unexpected response format")
        raise AIUnavailable("bad response") from e
    if not text:
        raise AIUnavailable("empty response")
    return text


# ======================= STUDENT DATA -> AI CONTEXT =======================
def recent_mistakes(db, user_id, topic_id, limit=4):
    """The student's latest DIFFERENT wrong answers on a topic."""
    rows = db.execute(
        "SELECT q.question_text, q.option_a, q.option_b, q.option_c, q.option_d, q.correct_option, "
        "q.explanation, aa.selected_option "
        "FROM attempt_answers aa "
        "JOIN quiz_attempts a ON a.id = aa.attempt_id "
        "JOIN questions q ON q.id = aa.question_id "
        "WHERE a.user_id = ? AND a.topic_id = ? AND a.completed_at IS NOT NULL AND aa.is_correct = 0 "
        "ORDER BY aa.id DESC",
        (user_id, topic_id),
    ).fetchall()
    seen, result = set(), []
    for r in rows:
        if r["question_text"] in seen:
            continue
        seen.add(r["question_text"])
        chosen = r["selected_option"]
        result.append({
            "question": r["question_text"],
            "student_answer": r["option_" + chosen.lower()] if chosen in LETTERS else "(no answer)",
            "correct_answer": r["option_" + r["correct_option"].lower()],
            "explanation": r["explanation"] or "",
        })
        if len(result) >= limit:
            break
    return result


def student_context(db, user_id, topic_id=None):
    """Collects what the system knows about this student. This is what makes the AI personalised."""
    profile = db.execute("SELECT grade FROM student_profiles WHERE user_id = ?", (user_id,)).fetchone()
    weak = db.execute(
        "SELECT t.name FROM topic_performance p JOIN topics t ON t.id = p.topic_id "
        "WHERE p.user_id = ? AND p.status = 'weak' ORDER BY p.accuracy LIMIT 3",
        (user_id,),
    ).fetchall()
    ctx = {
        "grade": profile["grade"] if profile else 7,
        "weak_topics": [w["name"] for w in weak],
        "topic": None, "code": None, "subject": None,
        "status": "new", "accuracy": 0, "mistakes": [],
    }
    if topic_id:
        t = db.execute(
            "SELECT t.name, t.code, s.name AS subject FROM topics t JOIN subjects s ON s.id = t.subject_id "
            "WHERE t.id = ?", (topic_id,)).fetchone()
        if t:
            ctx.update(topic=t["name"], code=t["code"], subject=t["subject"])
            perf = db.execute(
                "SELECT status, accuracy FROM topic_performance WHERE user_id = ? AND topic_id = ?",
                (user_id, topic_id)).fetchone()
            if perf:
                ctx.update(status=perf["status"], accuracy=perf["accuracy"])
            ctx["mistakes"] = recent_mistakes(db, user_id, topic_id)
    return ctx


LEVEL_HINTS = {
    "weak": "The student finds this topic difficult. Use very simple words, tiny steps and one very easy example.",
    "average": "The student knows the basics. Explain clearly and include one example of medium difficulty.",
    "strong": "The student is strong in this topic. Be brief and add one small challenge.",
    "new": "The student has not practised this topic here yet. Start from the basics for their class.",
}


def mistakes_text(mistakes):
    return "\n".join(
        "- Question: %s | Student answered: %s | Correct answer: %s" %
        (m["question"], m["student_answer"], m["correct_answer"]) for m in mistakes)


def build_system_prompt(ctx):
    lines = [
        "You are VidyaAI, a friendly tutor for a Class %d student in India (school syllabus)." % ctx["grade"],
        "Use simple English and short sentences. When helpful, use an everyday example (market, farm, cricket, roti, bus).",
        "Rules:",
        "- Teach the idea first. If the student pastes a homework or quiz question, do NOT give the final answer straight away. "
        "Give a hint or a similar worked example, then ask the student to try. Give the full answer only if they have tried and are still stuck.",
        "- Use the earlier messages to answer follow-up questions.",
        "- Stay on school subjects. If asked about something else, politely bring the student back to learning.",
        "- Keep the reply under 180 words. Plain text only: no markdown, no asterisks, no headings.",
        "- End with one short question or small task to check understanding.",
    ]
    if ctx["topic"]:
        lines.append("Current topic: %s (%s). The student's level in this topic is '%s' with recent accuracy %d%%." %
                     (ctx["topic"], ctx["subject"], ctx["status"], round(ctx["accuracy"])))
        lines.append(LEVEL_HINTS[ctx["status"]])
        if ctx["mistakes"]:
            lines.append("Mistakes this student made recently in this topic. Address these misunderstandings:\n" +
                         mistakes_text(ctx["mistakes"]))
    elif ctx["weak_topics"]:
        lines.append("The student is currently weak in: " + ", ".join(ctx["weak_topics"]) + ".")
    return "\n".join(lines)


def history_to_contents(history):
    contents = []
    for h in history:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h["text"]}]})
    while contents and contents[0]["role"] == "model":    # the conversation must start with the student
        contents.pop(0)
    return contents


# ======================= OFFLINE FALLBACK =======================
def offline_lesson(ctx):
    lesson = LESSONS.get(ctx["code"]) if ctx["code"] else None
    if not lesson:
        return "Choose a topic above to see the built-in notes. Answering your own questions needs the AI tutor."
    return ("%s\n\n%s\n\nExample: %s" % (ctx["topic"], lesson["explain"], lesson["example"]))


def offline_mistakes(ctx):
    text = offline_lesson(ctx)
    if ctx["mistakes"]:
        text += "\n\nYour recent mistakes:"
        for m in ctx["mistakes"]:
            text += "\n\nQuestion: %s\nYour answer: %s\nCorrect answer: %s" % (
                m["question"], m["student_answer"], m["correct_answer"])
            if m["explanation"]:
                text += "\nWhy: " + m["explanation"]
    return text


# ======================= TUTOR AND "EXPLAIN MY MISTAKES" =======================
def tutor_reply(db, user_id, topic_id, message, history):
    """Returns (reply_text, source, note). source is 'ai' or 'offline'."""
    ctx = student_context(db, user_id, topic_id)
    if not is_configured():
        note = "The AI is not set up, so built-in notes are shown."
    elif not allow_call(user_id):
        note = "You reached the hourly AI limit, so built-in notes are shown."
    else:
        contents = history_to_contents(history) + [{"role": "user", "parts": [{"text": message}]}]
        try:
            return call_gemini(build_system_prompt(ctx), contents, max_tokens=1024), "ai", None
        except AIUnavailable:
            note = "The AI could not be reached, so built-in notes are shown."
    return offline_lesson(ctx), "offline", note


def explain_mistakes(db, user_id, topic_id):
    """Personalised explanation built from the student's own wrong answers (step 4 of the loop)."""
    ctx = student_context(db, user_id, topic_id)
    if is_configured() and allow_call(user_id):
        if ctx["mistakes"]:
            request_text = ("Here are questions I got wrong:\n" + mistakes_text(ctx["mistakes"]) +
                            "\n\nFor each one, tell me in one or two simple sentences what I probably misunderstood. "
                            "Then explain the main idea of the topic again with one new example. "
                            "End with one practice question for me to try (do not give its answer).")
        else:
            request_text = ("I have no wrong answers recorded yet. Give me a short revision of this topic "
                            "with one example, and end with one practice question (do not give its answer).")
        try:
            text = call_gemini(build_system_prompt(ctx),
                               [{"role": "user", "parts": [{"text": request_text}]}], max_tokens=1200)
            return text, "ai", None
        except AIUnavailable:
            note = "The AI could not be reached, so built-in notes and your saved explanations are shown."
    elif not is_configured():
        note = "The AI is not set up, so built-in notes and your saved explanations are shown."
    else:
        note = "You reached the hourly AI limit, so built-in notes are shown."
    return offline_mistakes(ctx), "offline", note


# ======================= AI-GENERATED QUESTIONS =======================
def clean_question(item):
    """Checks one AI question. Returns (text, options, correct, explanation) or None if anything is wrong."""
    try:
        text = str(item["question"]).strip()
        options = [re.sub(r"^[A-Da-d][\).:]\s+", "", str(o).strip()) for o in item["options"]]
        correct = str(item["correct"]).strip().upper()[:1]
        explanation = str(item.get("explanation", "")).strip()
    except (KeyError, TypeError, AttributeError):
        return None
    if not 10 <= len(text) <= 300:
        return None
    if len(options) != 4 or any(not o or len(o) > 120 for o in options):
        return None
    if len({o.lower() for o in options}) != 4:        # all four options must be different
        return None
    if correct not in LETTERS:
        return None
    if not explanation or len(explanation) > 400:
        return None
    return text, options, correct, explanation


def parse_questions(raw):
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("questions", [])
    return data if isinstance(data, list) else []


def add_questions_for_weak_topic(db, user_id, topic_id, difficulty):
    """If the topic is WEAK, ask the AI for fresh questions aimed at the student's mistakes and save them.
    Returns how many were added. Any problem simply returns 0 and the normal question bank is used."""
    perf = db.execute(
        "SELECT status FROM topic_performance WHERE user_id = ? AND topic_id = ?", (user_id, topic_id)).fetchone()
    if perf is None or perf["status"] != "weak" or not is_configured():
        return 0
    ai_count = db.execute("SELECT COUNT(*) FROM questions WHERE topic_id = ? AND source = 'ai'", (topic_id,)).fetchone()[0]
    if ai_count >= MAX_AI_QUESTIONS_PER_TOPIC or not allow_call(user_id):
        return 0

    ctx = student_context(db, user_id, topic_id)
    existing = [r["question_text"] for r in db.execute(
        "SELECT question_text FROM questions WHERE topic_id = ? ORDER BY id DESC LIMIT 8", (topic_id,))]
    system = ("You write multiple-choice questions for Class %d school students in India. "
              "Return ONLY a JSON array, with no other text." % ctx["grade"])
    prompt = (
        "Write %d NEW multiple-choice questions on the topic '%s' (%s) at difficulty %d "
        "(1 = easy direct recall, 2 = medium one-step application, 3 = hard multi-step or word problem).\n"
        "Do not repeat these existing questions:\n%s\n"
        "The student recently got these wrong. Target the same misunderstandings with different questions:\n%s\n"
        "Each array item must look like: {\"question\": \"...\", \"options\": [\"...\", \"...\", \"...\", \"...\"], "
        "\"correct\": \"A\", \"explanation\": \"one or two sentences on why the correct option is right\"}.\n"
        "Exactly 4 different options, exactly one correct, and no 'A)' prefixes in the options. "
        "Use simple English and plain text." % (
            NEW_QUESTIONS_PER_QUIZ, ctx["topic"], ctx["subject"], difficulty,
            "\n".join("- " + q for q in existing) or "(none)",
            mistakes_text(ctx["mistakes"]) or "(none recorded)")
    )
    try:
        raw = call_gemini(system, [{"role": "user", "parts": [{"text": prompt}]}], max_tokens=2048, json_mode=True)
        items = parse_questions(raw)
    except (AIUnavailable, ValueError):
        return 0

    added = 0
    for item in items[:NEW_QUESTIONS_PER_QUIZ]:
        q = clean_question(item)
        if q is None:
            continue
        text, options, correct, explanation = q
        if db.execute("SELECT 1 FROM questions WHERE topic_id = ? AND question_text = ?", (topic_id, text)).fetchone():
            continue
        db.execute(
            "INSERT INTO questions (topic_id, difficulty, language, question_text, option_a, option_b, option_c, "
            "option_d, correct_option, explanation, source) VALUES (?, ?, 'en', ?, ?, ?, ?, ?, ?, ?, 'ai')",
            (topic_id, difficulty, text, options[0], options[1], options[2], options[3], correct, explanation),
        )
        added += 1
    return added