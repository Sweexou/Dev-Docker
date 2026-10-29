import json
import os
import sqlite3
import signal
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


PORT = int(os.environ.get("PORT", "5000"))
GAME_SERVER_URL = os.environ.get("GAME_SERVER_URL", "http://127.0.0.1:4000")
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", str(Path(__file__).with_name("quiz.db"))))


def initialize_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY,
                player TEXT NOT NULL,
                score INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        columns = {row[1] for row in database.execute("PRAGMA table_info(scores)")}
        if "total" not in columns:
            database.execute("ALTER TABLE scores ADD COLUMN total INTEGER NOT NULL DEFAULT 5")


class Handler(BaseHTTPRequestHandler):
    def request_game(self, path, payload=None):
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if payload is not None else None
        )
        request = Request(
            f"{GAME_SERVER_URL.rstrip('/')}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/quiz":
            try:
                self.send_json(200, self.request_game("/quiz"))
            except (OSError, ValueError):
                self.send_json(502, {"error": "Le serveur de jeu est indisponible"})
            return
        if path in ("/health", "/api/scores"):
            try:
                with sqlite3.connect(DATABASE_PATH) as database:
                    if path == "/health":
                        database.execute("SELECT id FROM scores LIMIT 1").fetchone()
                        data = {"status": "ok"}
                    else:
                        database.row_factory = sqlite3.Row
                        rows = database.execute(
                            "SELECT * FROM scores ORDER BY (score * 1.0 / total) DESC, score DESC, id ASC LIMIT 100"
                        ).fetchall()
                        data = {"scores": [dict(row) for row in rows]}
                self.send_json(200, data)
            except sqlite3.Error:
                self.send_json(503, {"error": "Database is unavailable"})
            return
        if path != "/api/game/status":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            game = self.request_game("/status")
            self.send_json(200, {"message": "Hello from Python API", "game": game})
        except (OSError, ValueError):
            self.send_json(502, {"error": "Game server is unavailable"})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/scores":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                self.send_json(413, {"error": "Requete trop volumineuse (4096 octets maximum)"})
                return
            if length <= 0:
                self.send_json(400, {"error": "Request body is required"})
                return
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError()
            player = data.get("player")
            if not isinstance(player, str) or not 1 <= len(player.strip()) <= 50:
                raise ValueError()
            if not isinstance(data.get("answers"), list) or not isinstance(data.get("quizId"), str):
                raise ValueError()
            # JSON escapes can contain lone surrogates that UTF-8 and SQLite reject.
            json.dumps(data, ensure_ascii=False).encode("utf-8")
        except ValueError:
            self.send_json(400, {"error": "Pseudo (1-50 caracteres), quizId et reponses requis"})
            return
        try:
            result = self.request_game("/quiz/grade", {
                "quizId": data["quizId"], "answers": data["answers"],
            })
            score = result["score"]
        except HTTPError as error:
            if error.code in (400, 413):
                try:
                    self.send_json(error.code, json.load(error))
                except ValueError:
                    self.send_json(error.code, {
                        "error": "Requete trop volumineuse" if error.code == 413 else "Reponses invalides",
                    })
            else:
                self.send_json(502, {"error": "Le serveur de jeu est indisponible"})
            return
        except (OSError, ValueError, KeyError):
            self.send_json(502, {"error": "Le serveur de jeu est indisponible"})
            return
        try:
            with sqlite3.connect(DATABASE_PATH) as database:
                cursor = database.execute(
                    "INSERT INTO scores (player, score, total) VALUES (?, ?, ?)",
                    (player.strip(), score, result["total"]),
                )
                score_id = cursor.lastrowid
            self.send_json(201, {"id": score_id, "player": player.strip(), **result})
        except sqlite3.Error:
            self.send_json(503, {"error": "Database is unavailable"})


if __name__ == "__main__":
    initialize_database()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    stopping = threading.Event()

    def shutdown(signum, frame):
        if stopping.is_set():
            return
        stopping.set()
        print("Stopping API", flush=True)
        # shutdown must run outside the thread executing serve_forever.
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f"API listening on port {PORT}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
