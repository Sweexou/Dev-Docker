const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const port = process.env.PORT || 3000;
const apiUrl = process.env.API_URL || "http://127.0.0.1:5000";
const page = fs.readFileSync(path.join(__dirname, "index.html"));

http.createServer(async (req, res) => {
  const pathname = new URL(req.url, "http://localhost").pathname;
  if (req.method !== "GET" && !(req.method === "POST" && pathname === "/api/scores")) {
    res.writeHead(405, { Allow: "GET, POST" });
    return res.end("Method not allowed");
  }
  if (pathname === "/") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    return res.end(page);
  }
  if (pathname.startsWith("/api/")) {
    try {
      let body;
      if (req.method === "POST") {
        const chunks = [];
        let size = 0;
        for await (const chunk of req) {
          size += chunk.length;
          if (size > 4096) {
            res.writeHead(413, { "Content-Type": "application/json" });
            return res.end(JSON.stringify({ error: "Requete trop volumineuse" }));
          }
          chunks.push(chunk);
        }
        body = Buffer.concat(chunks);
      }
      const response = await fetch(`${apiUrl.replace(/\/$/, "")}${pathname}`, {
        method: req.method,
        body,
        headers: { "Content-Type": "application/json" },
        signal: AbortSignal.timeout(7000),
      });
      const data = await response.json();
      res.writeHead(response.status, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      });
      return res.end(JSON.stringify(data));
    } catch {
      res.writeHead(502, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ error: "API is unavailable" }));
    }
  }
  res.writeHead(404);
  res.end("Not found");
}).listen(port, "0.0.0.0", () => {
  console.log(`Front listening on port ${port}`);
});
