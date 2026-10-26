# Docker Quiz

Three services communicate over HTTP:

Browser -> NGINX front -> Python API -> Node game server

## Run with Docker

The current compose.yaml sets ports, environment variables and resource limits
directly. The local .env and .env.example are retained for a later configuration
step; their values are not referenced by this version of Compose. Internal ports
remain 80, 5000 and 4000. Keep DATABASE_PATH under /data to use the existing
persistent volume. NGINX's upstream stays api:5000.

The front is bound to 127.0.0.1 by default. The API and game server have no
published host ports and communicate over the existing game-network.

Resource limits are configured directly in compose.yaml. See the section below
for their meaning and benchmarks/README.md for measurements and scope.

```powershell
docker compose up --build -d
```

Open http://localhost:3000, enter a nickname, answer the twenty questions,
and submit to see your score, explanations, and the leaderboard.
NGINX serves index.html on container port 80 and proxies /api/ to api:5000.
The front image uses a multi-stage build: Node runs npm run build to prepare
dist/, then only the static output is copied into the NGINX runtime image.
The API calls game-server:4000. Only the front is published to the host.

depends_on orders service startup but does not wait for services to be ready.
Healthchecks and automatic restart policies are not enabled in this version.

## Limites CPU et RAM

Les limites dans compose.yaml empechent un service de monopoliser les ressources
de la machine. Elles fixent des plafonds, pas une allocation reservee : un service
au repos consomme seulement ce dont il a besoin.

| Service | cpus | mem_limit | Usage |
| --- | ---: | ---: | --- |
| front | 0.25 | 64m (64 MiB) | NGINX sert les fichiers statiques et relaie les appels API. |
| api | 2.0 | 128m (128 MiB) | Python traite les requetes et accede a SQLite. |
| game-server | 0.5 | 128m (128 MiB) | Node.js fournit les questions et corrige les reponses. |

### Processeur : cpus

cpus exprime un budget de temps processeur en equivalent de CPU logique.
Ainsi, 0.25 correspond a un quart de CPU, 0.5 a un demi-CPU et 2.0 a deux CPU.
Ce n'est pas un pourcentage de tous les processeurs de la machine, ni une
affectation a des coeurs precis. Quand le budget est atteint, Docker limite
le temps CPU du conteneur (throttling) : les reponses peuvent ralentir,
mais le conteneur n'est pas tue pour cette seule raison.

### Memoire : mem_limit

mem_limit fixe le plafond de memoire du conteneur. Le suffixe m utilise ici
correspond a des mebioctets : 128m = 128 x 1024 x 1024 octets.
La limite concerne l'ensemble du conteneur, pas seulement les objets Python
ou le tas JavaScript. Elle ne limite pas l'espace disque du volume SQLite.

Une limite RAM protege la machine, mais ne garantit pas l'absence d'OOM
(Out Of Memory). Si le conteneur ne peut plus obtenir de memoire dans son
budget, un processus peut etre tue et le conteneur peut s'arreter. Un code 137
peut indiquer un SIGKILL, mais ne suffit pas a prouver un OOM : verifier
State.OOMKilled avec docker inspect. Un arret normal doit rester au code 0.

### Choix et verification

Ces valeurs reprennent les benchmarks locaux documentes dans
[benchmarks/README.md](benchmarks/README.md). Avec 10 requetes simultanees
pendant 30 secondes, le premier plafond de 1 CPU pour l'API donnait trois
erreurs ; le test avec 2 CPU a termine sans erreur. Les plafonds RAM gardent
une marge au-dessus des pics observes. Ce test porte sur des lectures HTTP,
pas sur une forte charge d'ecriture des scores : il faut refaire les mesures
si la charge ou les fonctionnalites evoluent.

Apres modification des limites, recreer les services et observer leur usage :

```powershell
docker compose up -d
docker compose stats
```

Pour verifier les limites reellement appliquees et un eventuel OOM :

```powershell
docker compose ps -aq | ForEach-Object {
  docker inspect --format '{{.Name}} CPU={{.HostConfig.NanoCpus}} RAM={{.HostConfig.Memory}} OOM={{.State.OOMKilled}} Exit={{.State.ExitCode}}' $_
}
```

NanoCpus est exprime en milliardieme de CPU (1000000000 = 1 CPU), et Memory
en octets. Ne pas utiliser uniquement docker compose restart pour appliquer
une nouvelle configuration : cette commande ne recree pas les conteneurs.

## Scores and persistence

SQLite stores scores in /data/quiz.db inside the API container, backed by the
quiz-data named volume. The image creates /data with permissions for its user.
The volume survives container recreation and docker compose down.
docker compose down -v deletes the volume and its scores.

There are ten multiple-choice questions and ten fill-in-the-blank questions.
Text answers are compared without case sensitivity and with surrounding spaces
removed. Each correct answer earns one point. The leaderboard compares score
percentages; older five-question results keep their original denominator.

Fetch questions and submit answers (option indexes for choices, strings for blanks):

```powershell
Invoke-RestMethod http://localhost:3000/api/quiz
Invoke-RestMethod -Method Post -Uri http://localhost:3000/api/scores -ContentType 'application/json' -Body '{"player":"Alice","quizId":"docker-basics-v2","answers":[0,1,2,0,1,0,1,2,0,1,"FROM","COPY","WORKDIR","CMD","ps","logs","stop","up","down","ENV"]}'
Invoke-RestMethod http://localhost:3000/api/scores
```

The Node game server owns the questions and computes scores. Correct answers
are only returned after submission. The Python API saves the computed score;
clients cannot submit a score directly. Authentication and multiplayer are
not implemented. Each submission is a separate leaderboard entry.
Edit game-server/questions.js to change the questions (currently twenty).
Change the quiz ID when changing questions or answer order.
Local runs store quiz.db next to api/server.py unless DATABASE_PATH is set.

```powershell
docker compose down
```

Requires Node.js 20+ and Python 3. No third-party packages are needed.

## Run locally with the optional Node front

From the project root, run each command in a separate terminal:

```powershell
node game-server/server.js
```

```powershell
python api/server.py
```

```powershell
node front/server.js
```

Open http://localhost:3000 to play the quiz.

The game server listens on port 3001, the API on 5000, and the front on 3000.
Each service accepts a PORT environment variable to override its default.
The front serves the page and forwards the browser's status request to the API.
The API fetches the game server's status and adds its own message.
An unavailable upstream service returns HTTP 502 with a JSON error.

The Node front files are retained for local development but are not used
in the NGINX image. In Docker, the API's address is configured in nginx.conf
and the game server's address in compose.yaml.

The Python HTTP server is intended for this small demo, not production hosting.

## Benchmark

With all three services running:

```powershell
node scripts/benchmark.js
```

The read-only benchmark runs for 30 seconds with 10 concurrent requests.
BENCHMARK_SECONDS, BENCHMARK_CONCURRENCY, BENCHMARK_URL and BENCHMARK_LABEL
can be overridden as process environment variables. If the published front port changes,
set BENCHMARK_URL to the matching URL. Reports are written under benchmarks/.
