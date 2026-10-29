const http = require("node:http");
const quiz = require("./questions");

const port = process.env.PORT || 4000;
const startedAt = new Date().toISOString();
const normalize = value => value.trim().toLowerCase();

const server = http.createServer(async (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  const pathname = new URL(req.url, "http://localhost").pathname;
  function send(status, data) {
    res.writeHead(status);
    res.end(JSON.stringify(data));
  }
  if (req.method === "GET" && pathname === "/quiz") {
    return send(200, {
      quizId: quiz.id,
      questions: quiz.questions.map(({ id, type = "choice", text, options }) => ({ id, type, text, options })),
    });
  }
  if (req.method === "POST" && pathname === "/quiz/grade") {
    try {
      const chunks = [];
      let size = 0;
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 4096) return send(413, { error: "Requete trop volumineuse" });
        chunks.push(chunk);
      }
      const data = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
      if (data?.quizId !== quiz.id) return send(400, { error: "Quiz inconnu : rechargez la page" });
      if (!Array.isArray(data.answers) || data.answers.length !== quiz.questions.length ||
          data.answers.some((answer, index) => {
            const question = quiz.questions[index];
            return question.type === "text"
              ? typeof answer !== "string" || !answer.trim() || answer.length > 80
              : !Number.isInteger(answer) || answer < 0 || answer >= question.options.length;
          })) {
        return send(400, { error: "Repondez a toutes les questions" });
      }
      const results = quiz.questions.map((question, index) => ({
        id: question.id,
        correct: question.type === "text"
          ? question.accepted.some(answer => normalize(answer) === normalize(data.answers[index]))
          : data.answers[index] === question.correct,
        correctAnswer: question.type === "text" ? question.accepted[0] : question.options[question.correct],
        explanation: question.explanation,
      }));
      return send(200, { score: results.filter(result => result.correct).length, total: results.length, results });
    } catch {
      return send(400, { error: "Requete JSON invalide" });
    }
  }
  if (req.method !== "GET") {
    res.writeHead(405, { Allow: "GET" });
    return res.end(JSON.stringify({ error: "Method not allowed" }));
  }
  if (pathname !== "/status") {
    res.writeHead(404);
    return res.end(JSON.stringify({ error: "Not found" }));
  }
  res.end(JSON.stringify({
    status: "running",
    message: "Hello from Node game server",
    players: 0,
    startedAt,
  }));
}).listen(port, "0.0.0.0", () => {
  console.log(`Game server listening on port ${port}`);
});

let stopping = false;
function shutdown() {
  if (stopping) return;
  stopping = true;
  console.log("Stopping game server");
  server.close((error) => {
    if (error) console.error(error);
    process.exitCode = error ? 1 : 0;
  });
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
