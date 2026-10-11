"""Automated tests for VidyaAI.  Run from the backend folder:  python test_basic.py
Uses a temporary database, so your real data is not touched. No internet or AI key is needed."""
import os
import tempfile
import unittest

# These must be set BEFORE the app is imported
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GEMINI_API_KEY"] = ""

import seed
seed.main()                       # creates tables, subjects, topics and the question bank
from app import app               # noqa: E402


class VidyaAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        meta = app.test_client().get("/api/meta").get_json()
        cls.subject_ids = [s["id"] for s in meta["subjects"]]
        cls.fractions_id = next(t["id"] for s in meta["subjects"] for t in s["topics"] if t["code"] == "fractions")

    def register(self, email, password="Test1234"):
        client = app.test_client()          # each client has its own cookies, like a separate browser
        resp = client.post("/api/auth/register", json={
            "name": "Test Student", "email": email, "password": password,
            "grade": 7, "school": "Test School", "subjects": self.subject_ids})
        return client, resp

    def test_weak_password_rejected(self):
        _, resp = self.register("weak@test.com", password="abc")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "WEAK_PASSWORD")

    def test_register_then_me(self):
        client, resp = self.register("a@test.com")
        self.assertEqual(resp.status_code, 201)
        me = client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["profile"]["grade"], 7)
        self.assertNotIn("password", str(me.get_json()))      # the hash is never sent to the browser

    def test_duplicate_email_rejected(self):
        self.register("dup@test.com")
        _, resp = self.register("dup@test.com")
        self.assertEqual(resp.status_code, 409)

    def test_wrong_password_rejected(self):
        self.register("login@test.com")
        resp = app.test_client().post("/api/auth/login", json={"email": "login@test.com", "password": "Wrong1234"})
        self.assertEqual(resp.status_code, 401)

    def test_protected_pages_need_login(self):
        self.assertEqual(app.test_client().get("/api/student/dashboard").status_code, 401)

    def test_student_cannot_use_teacher_route(self):
        client, _ = self.register("role@test.com")
        self.assertEqual(client.get("/api/teacher/ping").status_code, 403)

    def test_feedback_loop_and_answer_privacy(self):
        client, _ = self.register("loop@test.com")
        resp = client.post("/api/quiz/start", json={"topic_id": self.fractions_id, "difficulty": "auto"})
        self.assertEqual(resp.status_code, 201)
        attempt_id = resp.get_json()["attempt_id"]

        # The correct answers must NOT be sent while the quiz is open
        quiz = client.get("/api/quiz/%d" % attempt_id).get_json()
        self.assertNotIn("correct_option", str(quiz))
        self.assertEqual(len(quiz["questions"]), 5)

        # Submit with no answers: score 0, so the topic must become WEAK
        submit = client.post("/api/quiz/%d/submit" % attempt_id, json={"answers": {}})
        self.assertEqual(submit.status_code, 200)
        self.assertEqual(submit.get_json()["score"], 0)

        result = client.get("/api/quiz/%d/result" % attempt_id).get_json()
        self.assertEqual(result["performance"]["status"], "weak")
        self.assertEqual(len(result["answers"]), 5)

        dash = client.get("/api/student/dashboard").get_json()
        self.assertIn("Fractions", [t["name"] for t in dash["weak"]])
        self.assertTrue(any(r["action_type"] == "revise" for r in dash["recommendations"]))

        # The same quiz cannot be submitted twice
        again = client.post("/api/quiz/%d/submit" % attempt_id, json={"answers": {}})
        self.assertEqual(again.status_code, 409)

    def test_student_cannot_see_another_students_result(self):
        owner, _ = self.register("owner@test.com")
        attempt_id = owner.post("/api/quiz/start", json={"topic_id": self.fractions_id}).get_json()["attempt_id"]
        owner.post("/api/quiz/%d/submit" % attempt_id, json={"answers": {}})

        other, _ = self.register("other@test.com")
        self.assertEqual(other.get("/api/quiz/%d/result" % attempt_id).status_code, 404)


if __name__ == "__main__":
    unittest.main()