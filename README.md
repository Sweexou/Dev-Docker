# Docker Quiz

Quiz Docker de 20 questions (QCM et textes à trous), corrigé côté serveur,
avec explications et classement SQLite persistant. Une bonne réponse vaut
un point ; les réponses texte ignorent la casse et les espaces autour du mot.

## Démarrer

Prérequis : Docker et le plugin Compose prenant en charge `!reset`.
Depuis la racine du dépôt :

```powershell
docker compose up --build -d --wait
```

Ouvrir http://127.0.0.1:3000, saisir un pseudo, répondre et valider.
Les corrections apparaissent sous les questions et le score rejoint le classement.

```powershell
docker compose ps            # État et santé des services
docker compose logs          # Journaux
docker compose stats         # Consommation CPU/RAM
docker compose stop          # Arrêter sans supprimer les conteneurs
docker compose down          # Supprimer les conteneurs et le réseau
```

## Architecture

Navigateur → front NGINX → API Python → serveur de jeu Node.
L'API écrit et lit les scores dans SQLite.

| Service | Rôle | Port interne | Accès depuis l'hôte |
| --- | --- | ---: | --- |
| `front` | HTML/CSS/JavaScript et proxy `/api/` | 80 | `127.0.0.1:3000` |
| `api` | Relais vers le jeu et stockage SQLite | 5000 | Aucun port publié |
| `game-server` | Questions, validation et correction | 4000 | Aucun port publié |

Le réseau Compose `game-network` permet les communications par noms de services :
`api:5000` et `game-server:4000`. `localhost` désigne le conteneur lui-même.
`EXPOSE` documente un port ; seule la section `ports` le publie sur l'hôte.
Le proxy conserve les chemins `/api/*`.

Le [schéma éditable](docs/architecture.drawio) comporte les onglets application,
lint et tests.

## Images et étapes de build

| Image | Base et étapes | Dépendances |
| --- | --- | --- |
| Front | Build `node:20-alpine`, puis runtime `nginx:alpine`. `npm ci`, `npm run build`, copie de `dist/` et de `nginx.conf`. | Aucune dépendance npm applicative. `build.js` copie le HTML pour illustrer le multi-stage ; seul NGINX reste dans l'image finale. |
| API | `python:3.11-alpine`, création de l'utilisateur `python`, préparation de `/data`, copie des sources. | Bibliothèque standard Python ; aucun `pip install`. |
| Jeu | `node:20-alpine`, `npm ci`, copie des sources, `USER node`. | Modules Node natifs `node:http` et questions locales ; aucune dépendance npm tierce. |
| Lint | `node:20-alpine`, `apk add python3 py3-pip`, environnement `/opt/venv`, `npm ci` et installation de Ruff. | ESLint, `@eslint/js`, `globals`, `eslint-plugin-html` et Ruff épinglés dans les manifests. |
| Tests | `python:3.11-alpine`, utilisateur `tester`, copie du module de tests. | Bibliothèque standard Python ; aucun paquet supplémentaire. |

Les manifests npm sont copiés avant les sources pour réutiliser la couche
d'installation. `WORKDIR` prépare le dossier de travail ; `mkdir` crée le
répertoire de stockage ; `chown` et `COPY --chown` attribuent les fichiers aux
utilisateurs applicatifs. L'API et le jeu s'exécutent sans privilèges root.
NGINX conserve la configuration utilisateur de son image officielle.
Les `.dockerignore` excluent les fichiers locaux inutiles ; celui du lint
limite le contexte aux seuls fichiers de son outillage.

Les images finales sont personnalisées, mais leurs bases proviennent de Docker
Hub. La consigne « zéro image depuis Docker Hub » doit être clarifiée si elle
interdit également les images de base.

## Configuration et cycle de vie

Les valeurs par défaut permettent de démarrer sans `.env`. Le fichier
[.env.example](.env.example) répertorie les réglages. Compose lit `.env` ; les
variables du shell ont priorité. Seules les valeurs déclarées sous
`environment` sont transmises aux conteneurs.

| Variable | Défaut | Effet |
| --- | --- | --- |
| `FRONT_HOST`, `FRONT_PORT` | `127.0.0.1`, `3000` | Adresse et port publiés sur l'hôte |
| `FRONT_CPUS`, `FRONT_MEMORY` | `0.25`, `64m` | Plafonds du front |
| `API_CPUS`, `API_MEMORY` | `2.0`, `128m` | Plafonds de l'API |
| `GAME_CPUS`, `GAME_MEMORY` | `0.5`, `128m` | Plafonds du jeu |
| `GAME_SERVER_URL` | `http://game-server:4000` | Adresse du jeu vue par l'API |
| `DATABASE_PATH` | `/data/quiz.db` | Chemin SQLite ; conserver `/data` pour la persistance |
| `LINT_CPUS`, `LINT_MEMORY` | `1.0`, `256m` | Plafonds du job lint |
| `TEST_CPUS`, `TEST_MEMORY` | `1.0`, `128m` | Plafonds du job tests |

`cpus` fixe un plafond de temps CPU, sans réserver de cœur. `mem_limit` couvre
toute la mémoire du conteneur ; `128m` correspond à 128 MiB. Les allocations
retenues sont expliquées dans les [mesures de benchmark](benchmarks/README.md).
Les ports internes restent fixes à 80/5000/4000 ; `FRONT_PORT` change uniquement
le mapping de l'hôte. Après modification, appliquer `docker compose up -d --wait` :
un simple `restart` ne recharge pas la configuration Compose.

Les healthchecks interrogent la page front, `/health` de l'API (SQLite inclus)
et `/status` du jeu toutes les 10 secondes, avec un délai maximal de 5 secondes,
3 tentatives et une grâce initiale de 10 secondes. `depends_on` attend leur
réussite : jeu → API → front. Un échec ultérieur ne redémarre pas les services.

Les commandes JSON `CMD` évitent un shell intermédiaire. Le jeu hérite de
`docker-entrypoint.sh` et NGINX de `/docker-entrypoint.sh` ; l'API lance Python
directement. Python et Node traitent `SIGTERM`/`SIGINT` et ferment leur serveur ;
NGINX hérite de `SIGQUIT` pour l'arrêt normal. Docker impose son délai de grâce
avant un éventuel `SIGKILL`.

## API et persistance

| Route | Fonction |
| --- | --- |
| `GET /api/quiz` | Questions et identifiant du quiz, sans solutions |
| `POST /api/scores` | Corriger et enregistrer `player`, `quizId`, `answers` |
| `GET /api/scores` | Les 100 meilleurs scores |
| `GET /api/game/status` | État du jeu via l'API |

Les QCM utilisent des indices commençant à zéro ; les textes sont des chaînes
de 80 caractères maximum et le pseudo contient 1 à 50 caractères après trim.
Les corps JSON UTF-8 sont limités à 4 096 octets : un dépassement renvoie 413,
une soumission invalide 400, un échec d'amont 502. Le score envoyé par le client
est ignoré : seul le serveur de jeu le calcule.

Le volume `quiz-data`, monté sur `/data`, survit à la recréation des conteneurs
et à `docker compose down`. **`docker compose down -v` supprime les scores.**
Le classement trie par pourcentage décroissant, puis points décroissants,
puis identifiant croissant à égalité. Les anciens scores sur 5 restent lisibles.
Les soumissions successives créent des entrées distinctes.

Modifier `game-server/questions.js` pour changer le quiz, et changer son
identifiant si les questions ou leur ordre évoluent. Revoir alors les réponses
attendues indépendantes dans `tests/test_integration.py`.

## Lint et tests

```powershell
docker compose -f compose.lint.yaml up --build --abort-on-container-exit --exit-code-from lint
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from test
```

Les jobs renvoient 0 en cas de succès et 1 en cas d'échec. Le lint vérifie le
JavaScript, les scripts HTML et Python sans correction automatique. Ses sources
sont montées en lecture seule ; `network_mode: none` interdit le réseau au runtime.
Il n'a accès ni au volume SQLite, ni à `.env`, ni au socket Docker. Ses règles
sont dans `lint/eslint.config.mjs` et `lint/ruff.toml`.

Le projet `docker-quiz-test` lance une copie des trois services sans port publié,
avec son propre réseau et volume. `extends` réutilise les définitions ; seules
l'adresse interne du jeu, la base de test et la suppression des ports sont
surchargées. Conserver ce nom de projet distinct de l'application.

Les 12 tests couvrent les routes, la non-exposition des solutions, les corrections
parfaites/mixtes/fausses, la normalisation, Unicode (dont un caractère fragmenté
entre deux lectures réseau), les limites de taille, la validation sans écriture,
le stockage et le classement avec scores distincts et égalités. Le test de
fragmentation contacte directement le jeu sur `http://game-server:4000` ;
`TEST_GAME_URL` permet de cibler un lancement local. Ils ne pilotent pas le
navigateur et ne recréent pas les conteneurs pour tester la persistance.

Pour repartir d'une base de test neuve, puis nettoyer après validation :

```powershell
docker compose -f compose.test.yaml down -v
docker compose -f compose.lint.yaml down
```

Avec les noms par défaut, ces commandes ne touchent pas aux scores applicatifs.
Le téléchargement des outils et bases nécessite le réseau pendant le build.

## Benchmark et développement local

Le [benchmark](benchmarks/README.md) mesure des GET pendant 30 secondes avec
10 workers ; il ne mesure ni les écritures de scores ni le rendu navigateur.
Lancer `node scripts/benchmark.js` lorsque les trois services Docker tournent.
Réglages : `BENCHMARK_SECONDS`, `BENCHMARK_CONCURRENCY`, `BENCHMARK_URL` et
`BENCHMARK_LABEL`. Les rapports de même label dans `benchmarks/` sont écrasés.

Pour développer sans Docker, utiliser Node.js 20+ et Python 3, sans dépendances
applicatives tierces. Lancer dans trois terminaux depuis la racine :

```powershell
node game-server/server.js
python api/server.py
node front/server.js
```

Le front Node est réservé au développement local. Il utilise `PORT` et
`API_URL` (défaut `http://127.0.0.1:5000`). Le jeu et l'API utilisent aussi `PORT`.
Sans configuration, les ports sont 3000/5000/4000 et SQLite est stocké dans
`api/quiz.db` ; `DATABASE_PATH` permet de choisir une base temporaire.
L'application est une démonstration : pas d'authentification ni de multijoueur,
et le serveur HTTP Python standard n'est pas destiné à la production.
