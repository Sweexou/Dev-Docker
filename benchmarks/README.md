# Resource benchmark

Measured on 2026-10-08 using Docker Desktop's Linux engine with 16 logical CPUs
and approximately 7.47 GiB of available engine memory. Node runs the load
generator on the host. Each run lasts 30 seconds with 10 concurrent workers,
cycling through GET /api/quiz, GET /api/game/status and GET /api/scores.
Response bodies are read and parsed. Non-2xx responses and request errors count
as failures. Docker stats is sampled asynchronously approximately every three
seconds; observed peaks can miss short spikes.

## Results

| Run | Requests | Failures | Requests/s | Median ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline, no limits | 15,131 | 0 | 504.0 | 13.9 | 39.4 |
| First limits, API 1 CPU | 10,741 | 3 | 346.3 | 13.6 | 59.3 |
| Final limits, API 2 CPUs | 15,263 | 0 | 508.7 | 13.7 | 24.9 |

Raw measurements and Docker samples are in baseline.json, limited.json and
limited-final.json. The first limited run had failures and is retained as
evidence for adjusting the API allocation; its failure types were not recorded.
The final script records failure types for future runs.

## Final allocation

| Service | CPU ceiling | Memory ceiling | Final observed CPU peak | Final observed memory peak |
| --- | ---: | ---: | ---: | ---: |
| Front NGINX | 0.25 | 64 MiB | 24.75% | 19.76 MiB |
| Python API | 2 | 128 MiB | 190.04% | 39.00 MiB |
| Node game server | 0.5 | 128 MiB | 46.72% | 65.16 MiB |

Docker's 100% CPU represents approximately one logical CPU. Memory ceilings
retain headroom over observed usage. CPU ceilings cap use; they do not reserve
cores. The first API limit was too restrictive for this workload, so its
ceiling was raised to two CPUs and the same workload rerun successfully.
The front and game server ceilings were sufficient for this run.

These are short local measurements, not production capacity guarantees. They
exclude score-write load, large databases, browser rendering and multiplayer.
Single runs cannot establish that limits improve performance; the small
throughput difference between baseline and final run is normal test variation.
Retest if the workload or machine changes.

## Repeat

```powershell
docker compose up -d --wait
$env:BENCHMARK_LABEL = 'benchmark'
$env:BENCHMARK_SECONDS = '30'
$env:BENCHMARK_CONCURRENCY = '10'
node scripts/benchmark.js
```

Change BENCHMARK_URL if you change the public port in .env. Reports with the
same label are overwritten. To benchmark without ceilings, temporarily override
FRONT_CPUS, API_CPUS and GAME_CPUS with 0, and FRONT_MEMORY, API_MEMORY and
GAME_MEMORY with 0; recreate services, measure, then remove those process
overrides and recreate services to restore the .env limits.
