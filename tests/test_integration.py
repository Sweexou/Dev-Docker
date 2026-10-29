import json
import os
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = os.environ.get("TEST_BASE_URL", "http://front").rstrip("/")
# Independent expected answers: changing the quiz requires reviewing this fixture.
ANSWERS = {
    "dockerfile": 0, "build": 1, "container": 2, "volume": 0, "compose": 1,
    "run": 0, "ports": 1, "network": 2, "nginx": 0, "sqlite": 1,
    "from": "FROM", "copy": "COPY", "workdir": "WORKDIR", "cmd": "CMD",
    "ps": "ps", "logs": "logs", "stop": "stop", "up": "up", "down": "down",
    "env": "ENV",
}


def request(path, payload=None, raw=None):
    body = raw if raw is not None else (
        json.dumps(payload).encode("utf-8") if payload is not None else None
    )
    req = Request(BASE_URL + path, data=body, headers={"Content-Type": "application/json"})
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        content = response.read().decode("utf-8")
        if "application/json" in response.headers.get("Content-Type", ""):
            content = json.loads(content)
        return response.status, content


class QuizIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        status, cls.quiz = request("/api/quiz")
        if status != 200:
            raise AssertionError(f"Quiz unavailable: HTTP {status}: {cls.quiz}")
        cls.answers = [ANSWERS[q["id"]] for q in cls.quiz["questions"]]

    def payload(self, **changes):
        return {
            "player": "test-" + uuid.uuid4().hex,
            "quizId": self.quiz["quizId"],
            "answers": self.answers.copy(),
            **changes,
        }

    def answers_with(self, question_id, value):
        return [value if question["id"] == question_id else answer
                for question, answer in zip(self.quiz["questions"], self.answers)]

    def submit(self, payload, expected=201):
        status, result = request("/api/scores", payload)
        self.assertEqual(status, expected, result)
        return result

    def test_front_serves_quiz_page(self):
        status, html = request("/")
        self.assertEqual(status, 200)
        self.assertIn('<form id="quiz-form">', html)

    def test_quiz_contract_and_solution_redaction(self):
        self.assertEqual(self.quiz["quizId"], "docker-basics-v2")
        self.assertEqual(len(self.quiz["questions"]), 20)
        self.assertEqual({q["id"] for q in self.quiz["questions"]}, set(ANSWERS))
        for question in self.quiz["questions"]:
            with self.subTest(question=question["id"]):
                self.assertTrue(question["text"])
                self.assertFalse({"correct", "accepted", "explanation"} & question.keys())
                self.assertIn(question["type"], ("choice", "text"))

    def test_full_marks_normalization_and_saved_score(self):
        answers = [f" {answer.swapcase()} " if isinstance(answer, str) else answer
                   for answer in self.answers]
        payload = self.payload(answers=answers)
        result = self.submit(payload)
        self.assertEqual((result["score"], result["total"]), (20, 20))
        self.assertEqual(len(result["results"]), 20)
        for correction in result["results"]:
            self.assertTrue(correction["correct"])
            self.assertTrue(correction["correctAnswer"])
            self.assertTrue(correction["explanation"])
        # A later, separate HTTP request must read the committed database row.
        status, ranking = request("/api/scores")
        self.assertEqual(status, 200)
        stored = next(row for row in ranking["scores"] if row["id"] == result["id"])
        self.assertEqual(stored["player"], payload["player"])
        self.assertEqual((stored["score"], stored["total"]), (20, 20))
        self.assertTrue(stored["created_at"])

    def test_wrong_answers_ignore_forged_client_score(self):
        answers = ["incorrect" if q["type"] == "text" else (answer + 1) % len(q["options"])
                   for q, answer in zip(self.quiz["questions"], self.answers)]
        result = self.submit(self.payload(answers=answers, score=20, total=20))
        self.assertEqual(result["score"], 0)
        self.assertTrue(all(not item["correct"] for item in result["results"]))

    def test_mixed_answers_are_graded_individually(self):
        answers = self.answers_with("dockerfile", 1)
        result = self.submit(self.payload(answers=answers))
        self.assertEqual(result["score"], 19)
        for correction in result["results"]:
            self.assertEqual(correction["correct"], correction["id"] != "dockerfile")

    def test_invalid_submissions_do_not_create_scores(self):
        status, before = request("/api/scores")
        self.assertEqual(status, 200)
        invalid = [
            {"player": " "}, {"player": "x" * 51}, {"quizId": "obsolete"},
            {"answers": []}, {"answers": "invalid"},
            {"answers": self.answers_with("dockerfile", True)},
            {"answers": self.answers_with("dockerfile", -1)},
            {"answers": self.answers_with("dockerfile", 999)},
            {"answers": self.answers_with("from", " ")},
            {"answers": self.answers_with("from", "x" * 81)},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                result = self.submit(self.payload(**changes), expected=400)
                self.assertIn("error", result)
        for raw in (b"{", b"[]", b"null", b"x" * 4097):
            with self.subTest(raw=raw[:20]):
                status, result = request("/api/scores", raw=raw)
                self.assertEqual(status, 400, result)
        status, after = request("/api/scores")
        self.assertEqual(status, 200)
        self.assertEqual(after, before)

    def test_leaderboard_order(self):
        self.submit(self.payload())
        status, ranking = request("/api/scores")
        self.assertEqual(status, 200)
        rows = ranking["scores"]
        self.assertLessEqual(len(rows), 100)
        keys = [(-row["score"] / row["total"], -row["score"], row["id"]) for row in rows]
        self.assertEqual(keys, sorted(keys))

    def test_game_status_through_all_services(self):
        status, data = request("/api/game/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["game"]["status"], "running")

    def test_unknown_routes(self):
        for path in ("/missing", "/api/missing"):
            with self.subTest(path=path):
                status, _ = request(path)
                self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
