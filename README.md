# Docker Quiz

A 20-question Docker quiz with multiple-choice and fill-in-the-blank answers,
server-side grading, and a persistent leaderboard. Text answers ignore case and
surrounding whitespace. Each correct answer earns one point.

## Quick Start

Requires Docker with the Compose plugin. Start all three application services
from the repository root:

```powershell
docker compose up --build -d --wait
```

Open http://127.0.0.1:3000, enter a nickname, and submit your answers to see the
score and explanations.

```powershell
docker compose ps        # Show service and health status
docker compose logs      # Read service logs
docker compose stop      # Stop containers without removing them
docker compose down      # Remove containers and the application network
```

## Architecture and Ports

Browser -> NGINX front -> Python API -> Node game server

| Service | Responsibility | Internal port | Host access |
| --- | --- | ---: | --- |
| `front` | Serve HTML/CSS/JavaScript and proxy `/api/` to `api:5000`. | 80 | `127.0.0.1:3000` by default. |
| `api` | Forward quiz requests and store/read scores in SQLite. | 5000 | Not published. |
| `game-server` | Provide questions, validate answers, and calculate scores. | 4000 | Not published. |

All three services share the `game-network` bridge network and use service names
for internal DNS. Inside a container, `localhost` refers to that container, not
another service or the host.

Dockerfile `EXPOSE` instructions document internal ports; they neither publish
ports nor configure the application listener. Only the front has a Compose
`ports` mapping. Binding it to `127.0.0.1` restricts host access to the local machine.

The editable communication diagram is [docs/architecture.drawio](docs/architecture.drawio).

## Application Images

Compose builds each image from its service directory. Official Alpine-based
images provide compact runtime environments; each resulting image includes our
own code or configuration.

| Image | Base images | Customization and dependencies |
| --- | --- | --- |
| Front | `node:20-alpine` for build, `nginx:alpine` for runtime. | Custom `index.html` and `nginx.conf`. Node/npm prepare static files; only NGINX runs in the final image. |
| API | `python:3.11-alpine`. | Custom `server.py` and a dedicated non-root user. Uses Python's standard library: HTTP server, URL requests, JSON, SQLite, signals, threading, OS and path utilities. No third-party Python packages. |
| Game server | `node:20-alpine`. | Custom `server.js` and `questions.js`. Uses native `node:http`, built-in `fetch`, and the local questions module. No third-party npm packages. |

### Build Steps

The front and game server copy `package.json` and `package-lock.json` before
their source files and run `npm ci`. This uses the lockfile and allows Docker to
reuse the dependency layer when only application code changes. Neither
application currently declares third-party npm dependencies.

For the front, `npm run build` runs `build.js`, using native `node:fs` and
`node:path` to create `dist/` and copy `index.html`. This is static-file
preparation rather than a framework compilation. `COPY --from=build` transfers
the output to `/usr/share/nginx/html/` in the final NGINX image. The custom
configuration replaces `/etc/nginx/conf.d/default.conf`. Node and build tools
are not included in the runtime image.

The API copies its Python source directly; no `pip install` is required.
Application images install no additional OS packages. Their healthchecks reuse
the existing `wget`, Python, or Node executable.

### OS Operations and Permissions

Build instructions operate inside image layers, not on the host OS.

| Operation | Purpose |
| --- | --- |
| `WORKDIR /app` | Create the working directory if needed and set it for subsequent relative paths. Used by the front build, API, and game server. |
| API: `addgroup -S python`, `adduser -S -G python python` | Create a system group and user that are not provided as application accounts by the Python base image. |
| API: `mkdir -p /data` | Prepare the SQLite volume mount point. |
| API: `chown -R python:python /app /data` | Give the application user access to the code and permission to write database files. |
| Game server: `chown -R node:node /app` | Give the existing Node image user ownership of the working directory. |
| `USER python` / `USER node` | Run the API and game server without root privileges. |
| `COPY --chown=...` | Assign source-file ownership during the copy. |

The front retains the NGINX image's user and worker configuration; its Dockerfile
does not explicitly switch the whole container to a non-root user.

The front's `.dockerignore` excludes local dependencies and generated output.
The API's excludes Python caches and local SQLite files. The game server does
not currently have a dedicated `.dockerignore`.

## Entrypoints and Shutdown

`ENTRYPOINT` defines an image's launch program; `CMD` supplies the default
command or arguments. These Dockerfiles retain their base entrypoints where
present.

| Service | Startup | Reason |
| --- | --- | --- |
| Front | Inherited `/docker-entrypoint.sh`, then `nginx -g 'daemon off;'`. | Preserve NGINX initialization and keep the server in the foreground. |
| API | `CMD ["python", "server.py"]`; no base entrypoint script. | Launch the Python server directly from `/app`. |
| Game server | Inherited `docker-entrypoint.sh`, then `CMD ["node", "server.js"]`. | The base script hands execution to the Node server. |

JSON-form commands avoid an intermediate `/bin/sh -c`. The foreground process
determines the container lifetime and receives shutdown signals.

Python and Node handle `SIGTERM` and `SIGINT`: Python calls `server.shutdown()`
from a separate thread and closes the server; Node calls `server.close()`.
The official NGINX image uses `SIGQUIT` for graceful shutdown. Docker waits for
the shutdown grace period before forcing termination with `SIGKILL`. Previous
normal-stop tests returned exit code `0` for all three services.

## Runtime Configuration

Compose automatically reads the root `.env` file. Each
`${VARIABLE:-default}` expression uses its fallback if the variable is missing
or empty. Shell environment values take precedence over `.env`. The defaults
allow startup without a local configuration file; `.env.example` lists the
application settings.

Only values explicitly declared under `environment` are injected into
containers. Port and resource settings configure Docker itself. There are no
custom build-time `ARG` declarations.

| Variable | Default | Consumer and effect |
| --- | --- | --- |
| `FRONT_HOST` | `127.0.0.1` | Docker: host address for the front's published port. |
| `FRONT_PORT` | `3000` | Docker: host port mapped to container port 80. |
| `FRONT_CPUS` | `0.25` | Docker: front CPU ceiling. |
| `FRONT_MEMORY` | `64m` | Docker: front memory ceiling. |
| `API_CPUS` | `2.0` | Docker: API CPU ceiling. |
| `API_MEMORY` | `128m` | Docker: API memory ceiling. |
| `GAME_CPUS` | `0.5` | Docker: game-server CPU ceiling. |
| `GAME_MEMORY` | `128m` | Docker: game-server memory ceiling. |
| `GAME_SERVER_URL` | `http://game-server:4000` | Python environment: upstream game-server address. |
| `DATABASE_PATH` | `/data/quiz.db` | Python environment: SQLite path, which must stay under `/data` for persistence. |

The game server defaults to port 4000 in Docker and local development; the
Python API defaults to 5000. Internal ports are fixed in this stack: changing
one also requires updating its callers and healthcheck. `FRONT_PORT` changes
only the host mapping.

For example, a local `.env` can contain:

```dotenv
FRONT_PORT=3100
API_MEMORY=256m
```

Reapply configuration with `docker compose up -d --wait`; this example exposes
the front at http://127.0.0.1:3100. A plain `docker compose restart` does not
apply configuration changes. To select a file explicitly, add
`--env-file .env` before `up`. Keep `.env` out of Git.

### CPU and Memory Limits

These are ceilings, not reservations. `cpus` expresses a budget in logical-CPU
equivalents: 0.25 is one quarter of a CPU, while 2.0 allows two CPUs' worth of
processing time. Reaching the ceiling throttles execution rather than killing
the container; it does not pin the service to specific cores.

`mem_limit` covers the entire container's memory, not just the Python or
JavaScript heap. The `m` suffix represents MiB: `128m` is 134,217,728 bytes.
It does not limit the SQLite volume's disk space. A process may be killed if
the memory budget is exhausted. Exit code 137 indicates a `SIGKILL`, but
`State.OOMKilled` must be checked before attributing it to an OOM event.

The selected limits retain memory headroom over observed usage. In the
30-second, 10-worker read-only benchmark, the first API ceiling of one CPU
produced three failed requests; the final two-CPU run completed without errors.
See [benchmark results](benchmarks/README.md) and the raw JSON reports in
`benchmarks/`. These measurements do not establish capacity for heavy writes.

Monitor consumption with `docker compose stats`. Inspect applied ceilings and
shutdown results with:

```powershell
docker compose ps -aq | ForEach-Object {
  docker inspect --format '{{.Name}} CPU={{.HostConfig.NanoCpus}} RAM={{.HostConfig.Memory}} OOM={{.State.OOMKilled}} Exit={{.State.ExitCode}}' $_
}
```

`NanoCpus` uses billionths of a CPU; `Memory` is in bytes. Validate the resolved
Compose configuration with `docker compose config --quiet`.

### Healthchecks and Startup Order

Every 10 seconds, Docker probes the front page, the API's `/health` route
(including SQLite access), and the game server's `/status` route. Checks have
a 5-second timeout, three retries, and a 10-second startup grace period.

`depends_on: condition: service_healthy` starts the game server first, then the
API after the game server is healthy, then the front after the API is healthy.
An unhealthy status after startup does not automatically restart the container
or stop its dependents. No automatic restart policy is configured.

## Scores and Persistence

The API writes SQLite scores to the `quiz-data` named volume mounted at
`/data`. It survives container recreation and `docker compose down`.
**Running `docker compose down -v` deletes the volume and its scores.**

The API accepts answers, not a client-calculated score. The game server grades
them and returns explanations after submission. Each submission adds a
leaderboard entry; ranking compares percentages so older five-question scores
retain their original denominator. Authentication and multiplayer are not
implemented.

| API route | Purpose |
| --- | --- |
| `GET /api/quiz` | Return the quiz ID and questions without solutions. |
| `POST /api/scores` | Accept `player`, `quizId`, and an `answers` array; grade and save the result. Choices use zero-based indexes; blanks use strings. |
| `GET /api/scores` | Return up to 100 leaderboard entries. |
| `GET /api/game/status` | Return the game-server status through the API. |

Edit `game-server/questions.js` to update the questions. Change the quiz ID
whenever questions or answer order change.

## Lint Container

Lint runs independently of the application under the separate Compose project
`docker-quiz-lint`:

```powershell
docker compose -f compose.lint.yaml up --build --abort-on-container-exit --exit-code-from lint
```

The one-shot job exits with `0` when all checks pass and `1` if a check fails.
`--exit-code-from lint` forwards that result to the caller for CI use. It runs
without automatic fixes; it does not execute functional tests.

### Lint Image and Dependencies

`lint/Dockerfile` customizes `node:20-alpine` with these tools:

| Dependency | Installation | Purpose |
| --- | --- | --- |
| ESLint and `@eslint/js` | `npm ci --no-audit --no-fund` using the lint lockfile. | Recommended JavaScript checks, including undefined names and unused variables. |
| `globals` | Same npm installation. | Declare Node and browser globals for the appropriate source files. |
| `eslint-plugin-html` | Same npm installation. | Lint inline JavaScript in HTML; it does not validate HTML or CSS. |
| Python and pip | `apk add --no-cache python3 py3-pip`. | Provide the Python runtime and installer required for Ruff. |
| Ruff | `pip install --no-cache-dir -r requirements.txt` inside `/opt/venv`. | Check Python using rule groups E4, E7, E9, and F. Its version is pinned in `lint/requirements.txt`. |

`python3 -m venv /opt/venv` isolates Ruff from system packages. Tools and
configuration live under `WORKDIR /opt/lint`; manifests are copied before
scripts so installation layers can be cached. `lint/Dockerfile.dockerignore`
restricts the build context to lint files, excluding application sources and
local configuration from the image.

The final working directory is `/workspace`, and `USER node` selects the
base image's non-root account. The JSON command
`CMD ["node", "/opt/lint/run.mjs"]` runs through the inherited Node entrypoint.
The runner executes ESLint and Ruff sequentially and preserves a failed result
from either tool.

### Lint Isolation and Configuration

The application directories, benchmark scripts, and tests are
mounted read-only. The container receives neither the SQLite volume, `.env`,
nor the Docker socket. Generated `dist/` and `node_modules/` directories are
ignored by ESLint; Ruff runs without a cache. Rules are defined in
`lint/eslint.config.mjs` and `lint/ruff.toml`.

No ports are published. `network_mode: none` disables runtime networking;
building the image still requires network access to download tools and bases.
The lint Compose file accepts `LINT_CPUS` (default `1.0`) and `LINT_MEMORY`
(default `256m`) from the shell or `.env` as resource ceilings.

Remove the finished lint container with:

```powershell
docker compose -f compose.lint.yaml down
```

Tool references: [ESLint](https://eslint.org/docs/latest/use/),
[HTML script linting](https://github.com/BenoitZugmeyer/eslint-plugin-html),
and [Ruff installation](https://docs.astral.sh/ruff/installation/).

## Test Container

The second CI job runs functional integration tests against a separate copy of
the three application services. It uses the `docker-quiz-test` Compose project:

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from test
```

Compose waits for the game server, API, and front healthchecks before launching
the one-shot `test` service. `--exit-code-from test` returns the test result to
the caller: `0` on success and `1` for a failed assertion or test error. The
other application services are stopped when the job exits. There are no host
port mappings, so the normal quiz stack can run at the same time.

`compose.test.yaml` reuses application definitions through `extends`, resets
the front's published ports with `!reset []`, and forces test API addresses and
the database path. Use a current Docker Compose plugin supporting `!reset`.
Its network and `quiz-data` volume are scoped to the test project. Test scores
never enter the normal project's volume. Keep the test project name distinct
when using `-p` or `COMPOSE_PROJECT_NAME` overrides.

Start each run with a fresh test volume by cleaning up the previous run:

```powershell
docker compose -f compose.test.yaml down -v
```

This command removes only the test project's resources when invoked with its
default project name; it does not remove normal application scores. Run it
after the job too when the test results and logs are no longer needed.

### Test Image, Resources, and Coverage

`tests/Dockerfile` customizes `python:3.11-alpine` with the test source. Python's
standard-library `unittest`, `urllib`, JSON, OS, and UUID modules provide the
runner, HTTP client, assertions, configuration, and unique test nicknames.
There are no pip dependencies or extra OS packages to install.

`WORKDIR /tests` creates/selects the source directory. `addgroup` and `adduser`
create the unprivileged `tester` account; `USER tester` selects it for runtime.
Copied source stays root-owned and readable by that user. The `.dockerignore`
allows only the test module into the build context. No source bind mounts,
database mounts, or Docker socket are given to the test container.

The exec-form `CMD ["python", "-m", "unittest", "discover", "-v"]` runs Python
directly in the foreground without a shell or custom entrypoint. Completion
ends the container; Docker can send termination signals directly to Python.
`PYTHONDONTWRITEBYTECODE=1` prevents source-directory cache writes, and
`PYTHONUNBUFFERED=1` makes CI output appear immediately.

The test service uses `TEST_CPUS` (default `1.0`) and `TEST_MEMORY` (default
`128m`) as ceilings. This sequential HTTP client needs no reserved CPU cores;
these budgets bound the lightweight Python runner independently of the
application limits inherited from `compose.yaml`. `TEST_BASE_URL=http://front`
is passed to the runner; each HTTP request has a 10-second timeout.

The nine tests cover front HTML serving, quiz schema and solution redaction,
perfect/mixed/incorrect grading, text normalization, rejection of a forged
client score, saved-score retrieval, leaderboard ordering, invalid inputs
without database writes, cross-service status, and unknown routes. Expected
answers are an independent fixture in `tests/test_integration.py`; review it
when changing questions or the quiz ID. Score storage is checked through a
later HTTP request; container-recreation persistence and browser interactions
are not covered by this suite.

The editable architecture diagram includes a **Tests CI** tab for this job.
Lint and tests remain separate containers and can be invoked independently.

## Benchmark

With the three application services running:

```powershell
node scripts/benchmark.js
```

The benchmark sends read-only requests for 30 seconds with 10 concurrent
workers. Configure it through `BENCHMARK_SECONDS`, `BENCHMARK_CONCURRENCY`,
`BENCHMARK_URL`, and `BENCHMARK_LABEL` in the shell. Set the URL if the front's
public port changes. Reports are saved in `benchmarks/`; runs with the same
label overwrite the previous report.

## Local Development without Docker

Requires Node.js 20+ and Python 3, with no third-party application packages.
Run these commands in separate terminals from the repository root:

```powershell
node game-server/server.js
python api/server.py
node front/server.js
```

The optional Node front is only used for local development. Default ports are
3000 for the front, 5000 for the API, and 4000 for the game server. Local SQLite
data is stored beside `api/server.py` unless `DATABASE_PATH` is set. The
standard-library Python HTTP server is intended for this demo, not production.
