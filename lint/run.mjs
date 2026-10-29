import { spawnSync } from "node:child_process";

const checks = [
  ["JavaScript et scripts HTML", "/opt/lint/node_modules/.bin/eslint", [
    "--config", "/opt/lint/eslint.config.mjs", "--max-warnings", "0",
    "front/**/*.js", "front/**/*.html", "game-server/**/*.js", "scripts/**/*.js",
    "server.js",
  ]],
  ["Python", "/opt/venv/bin/ruff", ["check", "--no-cache", "--config", "/opt/lint/ruff.toml", "api", "tests"]],
];

let failed = false;
for (const [name, executable, args] of checks) {
  console.log(`\nLint : ${name}`);
  const result = spawnSync(executable, args, { stdio: "inherit" });
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) failed = true;
}
console.log(failed ? "\nEchec du lint" : "\nTous les controles de lint ont reussi");
process.exitCode = failed ? 1 : 0;
