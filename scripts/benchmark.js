const { spawnSync, execFile } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");

const root = path.join(__dirname, "..");
const baseUrl = process.env.BENCHMARK_URL || "http://127.0.0.1:3000";
const seconds = Number(process.env.BENCHMARK_SECONDS || 30);
const concurrency = Number(process.env.BENCHMARK_CONCURRENCY || 10);
const label = process.env.BENCHMARK_LABEL || "benchmark";
if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 100 ||
    !Number.isFinite(seconds) || seconds < 1 || seconds > 300 || !/^[a-z0-9-]+$/i.test(label)) {
  throw new Error("Invalid benchmark duration, concurrency, or label");
}

function docker(args) {
  const result = spawnSync("docker", args, { cwd: root, encoding: "utf8", windowsHide: true });
  if (result.status !== 0) throw new Error(result.stderr || "Docker command failed");
  return result.stdout;
}

function memoryBytes(value) {
  const match = value.trim().match(/^([\d.]+)\s*(B|KiB|MiB|GiB|kB|MB|GB)$/);
  if (!match) throw new Error(`Unknown Docker memory unit: ${value}`);
  return Number(match[1]) * ({ B: 1, KiB: 1024, MiB: 1024 ** 2, GiB: 1024 ** 3, kB: 1000, MB: 1000 ** 2, GB: 1000 ** 3 }[match[2]]);
}

async function run() {
  const ids = docker(["compose", "ps", "-q"]).trim().split(/\s+/).filter(Boolean);
  if (ids.length !== 3) throw new Error("Start all three Compose services before benchmarking");
  const containers = JSON.parse(docker(["inspect", ...ids]));
  const snapshots = [];
  const latencies = [];
  let failures = 0;
  const failureDetails = {};
  function recordFailure(reason) {
    failures++;
    failureDetails[reason] = (failureDetails[reason] || 0) + 1;
  }
  const started = performance.now();
  const deadline = started + seconds * 1000;
  const routes = ["/api/quiz", "/api/game/status", "/api/scores"];
  const sample = async () => {
    const output = await new Promise((resolve, reject) => {
      execFile("docker", ["stats", "--no-stream", "--format", "{{json .}}", ...ids],
        { cwd: root, windowsHide: true }, (error, stdout) => error ? reject(error) : resolve(stdout));
    });
    const rows = output
      .trim().split(/\r?\n/).filter(Boolean).map(row => JSON.parse(row));
    snapshots.push({ elapsedSeconds: (performance.now() - started) / 1000, rows });
  };
  const sampling = (async () => {
    do {
      await sample();
      if (performance.now() < deadline) await new Promise(resolve => setTimeout(resolve, 1000));
    } while (performance.now() < deadline);
  })();
  // Attach the rejection handler immediately while requests are still in flight.
  let samplingError;
  const samplingDone = sampling.catch(error => { samplingError = error; });
  async function worker(index) {
    let sequence = index;
    while (performance.now() < deadline) {
      const time = performance.now();
      try {
        const response = await fetch(`${baseUrl}${routes[sequence++ % routes.length]}`, {
          signal: AbortSignal.timeout(10000),
        });
        await response.json();
        if (!response.ok) recordFailure(`HTTP ${response.status}`);
      } catch (error) { recordFailure(error.message); }
      latencies.push(performance.now() - time);
    }
  }
  await Promise.all(Array.from({ length: concurrency }, (_, index) => worker(index)));
  const elapsed = (performance.now() - started) / 1000;
  await samplingDone;
  if (samplingError) throw samplingError;
  latencies.sort((a, b) => a - b);
  const percentile = fraction => latencies[Math.max(0, Math.ceil(latencies.length * fraction) - 1)] || 0;
  const resources = containers.map(container => {
    const name = container.Name.slice(1);
    const rows = snapshots.flatMap(snapshot => snapshot.rows.filter(row => row.Name === name));
    return {
      service: container.Config.Labels["com.docker.compose.service"],
      peakCpuPercent: Math.max(...rows.map(row => parseFloat(row.CPUPerc))),
      peakMemoryMiB: Math.max(...rows.map(row => memoryBytes(row.MemUsage.split("/")[0]))) / 1024 ** 2,
      cpuLimit: container.HostConfig.NanoCpus / 1e9,
      memoryLimitMiB: container.HostConfig.Memory / 1024 ** 2,
    };
  });
  const report = {
    measuredAt: new Date().toISOString(), baseUrl, label, concurrency, requestedSeconds: seconds,
    elapsedSeconds: elapsed, requests: latencies.length, failures, failureDetails,
    requestsPerSecond: latencies.length / elapsed,
    latencyMs: { median: percentile(.5), p95: percentile(.95), max: latencies.at(-1) || 0 },
    resources, snapshots,
    scope: "Read-only GET /api/quiz, /api/game/status and /api/scores; excludes score writes, browser rendering and multiplayer. Docker stats sampled asynchronously; peaks are sampled observations, not absolute maxima.",
  };
  const output = path.join(root, "benchmarks", `${label}.json`);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({ ...report, snapshots: undefined }, null, 2));
  console.log(`Report: ${output}`);
  if (failures) process.exitCode = 1;
}

run().catch(error => { console.error(error.message); process.exitCode = 1; });
