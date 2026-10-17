# URL Shortener with Click Analytics

**Language:** Python (FastAPI) &nbsp;|&nbsp; **Needs:** Postgres + Redis &nbsp;|&nbsp; **DevOps:** Docker, Docker Compose, CircleCI, Kubernetes

A production-grade, containerized URL shortener and real-time click analytics platform engineered with automated branch promotion, CI/CD pipeline, and multi-namespace Kubernetes orchestration.

---

## 1. What this app needs

| Component | Specification |
|---|---|
| **Runtime** | Python 3.12 (`python:3.12.8-slim-bookworm`) |
| **Dependencies** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port 8080` |
| **Listens on** | Port 8080, bound to `0.0.0.0` |
| **Environment Variables** | `DATABASE_URL`, `REDIS_URL` |
| **Pre-requisites** | PostgreSQL 16, Redis 7, SQL migrations applied |

### Endpoints & Capabilities

```
GET    /                          Interactive Web UI Dashboard (forms, links table, analytics, CRUD actions)
GET    /health                    Health check returning reachability status for Postgres and Redis separately
POST   /shorten                   Create a short URL {"url": "https://...", "custom": "optional"}
GET    /{code}                    302 Redirect to target URL, increments click counter in Redis
GET    /api/links                 List recent links with real-time click counts
PUT    /api/links/{code}          Update destination URL for an existing short code
DELETE /api/links/{code}          Delete short code, cascading delete of clicks, purge Redis cache
GET    /api/links/{code}/stats    Detailed analytics: clicks per day and top referrers
```

### Migrations

`migrations/` holds `.sql` files applied **in filename order** before the application starts:
- `001_schema.sql`: Creates `links` and `clicks` tables, foreign keys with `ON DELETE CASCADE`, and unique index on `code`.
- `002_seed.sql`: Seeds initial URLs (`welcome`, `circleci`, `git`) and sample click events across a 14-day window.

---

## 2. Quickstart: Docker Compose

Start the full stack with automated migrations, health checks, and service dependency ordering:

```bash
docker compose up --build
```

Verify health check:
```bash
curl -s http://localhost:8080/health
```
```json
{"status":"ok","postgres":true,"redis":true}
```

Open the web dashboard:
```
http://localhost:8080/
```

### Full CRUD API Demonstration via curl

```bash
# 1. CREATE (Shorten a URL)
curl -s -X POST http://localhost:8080/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.docker.com", "custom": "docker"}'

# 2. READ (Redirect & Stats)
curl -s -I http://localhost:8080/docker
curl -s http://localhost:8080/api/links/docker/stats

# 3. UPDATE (Modify destination URL)
curl -s -X PUT http://localhost:8080/api/links/docker \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.docker.com/engine/"}'

# 4. DELETE (Remove link and purge cache)
curl -s -X DELETE http://localhost:8080/api/links/docker

# 5. VERIFY in Postgres database
docker compose exec postgres psql -U postgres -d url_shortener -c "SELECT id, code, url FROM links;"
```

---

## 3. The Hard Part: Concurrency and Collision Prevention

### The Challenge
> Two people shortening the same URL at the same moment must not get the same code. Decide whether identical URLs share a code or get separate ones, and make the collision impossible either way.

### The Architectural Decision: Separate Codes per Link
We chose to give identical URLs **separate short codes** upon each creation request.
- **Rationale:** In marketing, campaign management, and user telemetry, two distinct users (or departments) shortening the same landing page require **independent attribution**. If two users shared the same code, User A's promotional clicks would pollute User B's analytics, destroying campaign tracking accuracy.

### Making Collisions Impossible

#### 1. Auto-generated Codes (Atomic Database Sequence + Bijection)
- When a URL is shortened without a custom code, the app issues:
  ```sql
  INSERT INTO links (code, url) VALUES ('', %s) RETURNING id;
  ```
- PostgreSQL assigns a monotonically increasing integer `id` from an atomic internal sequence (`SERIAL`).
- Sequence increments in PostgreSQL are transactional, lock-free, and guaranteed atomic at the storage engine level. Even under extreme concurrency (millions of concurrent requests), no two transactions can ever receive the same `id`.
- The short code is computed via `encode(id)`, which converts the integer into base-58 using the custom alphabet `23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ`.
- Because base-58 encoding is a **strict mathematical bijection** (one-to-one and onto for positive integers), $\forall a, b \in \mathbb{N}^+: a \neq b \implies \text{encode}(a) \neq \text{encode}(b)$.
- **Conclusion:** Auto-generated code collision is mathematically and architecturally impossible.

#### 2. Custom Codes (Eliminating Time-of-Check to Time-of-Use Race Conditions)
- If two users submit the exact same custom code (e.g., `special2026`) in the same millisecond:
  - Application-level checking (`SELECT 1 FROM links WHERE code = %s`) suffers from a classic **TOCTOU** (Time-of-Check to Time-of-Use) race condition where both requests read "not taken" before either has committed.
  - To make collisions impossible, PostgreSQL enforces a database-level unique index:
    ```sql
    CREATE UNIQUE INDEX links_code ON links (code) WHERE code <> '';
    ```
  - When the second transaction attempts to commit the duplicate code, the PostgreSQL engine detects the conflict and rejects it with a `UniqueViolation` error.
  - The application catches this exception and converts it into a clean HTTP 409 Conflict (`'code' is already taken`).
- **Conclusion:** Custom code collisions are prevented by ACID database-level unique constraints, ensuring data integrity without race conditions.

---

## 4. Test Suite and Coverage

The repository provides two test suites:
1. **Unit Tests (`tests/test_codes.py`, `tests/test_app_unit.py`)**:
   - 152 tests covering base-58 alphabet rules, length bounds, reserved keywords, URL normalisation, SSRF protection (`is_safe`), and mocked controller workflows.
   - Zero external network or database dependencies.
   - Code coverage exceeds **93%** (comfortably surpassing the 70% requirement).
2. **Integration Tests (`tests/test_integration.py`)**:
   - 10 comprehensive tests running against real PostgreSQL and Redis service containers.
   - Validates `/health`, `/shorten`, redirects, Redis caching, `/api/links`, CRUD updates, deletions, and stats.

To run unit tests with coverage:
```bash
pytest tests/test_codes.py tests/test_app_unit.py --cov=app --cov-report=term-missing --cov-fail-under=70
```

---

## 5. CircleCI CI/CD Pipeline

The CircleCI configuration (`.circleci/config.yml`) implements strict branch gating and dual-tagging:

### Main (QA) Pipeline — Full Automated Quality Gate
Triggers on pull requests and commits to `main`:
1. **Secret Scanning:** `gitleaks` scans all files for exposed secrets, tokens, or private keys.
2. **Lint:** `ruff check .` validates code style and syntax.
3. **Unit Tests:** `pytest` runs unit tests and verifies code coverage $\ge 70\%$.
4. **Integration Tests:** Spins up official `cimg/postgres:16.0` and `cimg/redis:7.0` service containers on `localhost`, applies migrations, and runs end-to-end integration tests.
5. **Image Build & Push:** Uses `setup_remote_docker` to build the Docker image and push two tags to Docker Hub:
   - Moving tag: `<DOCKERHUB_USER>/url-shortener-python:qa`
   - Immutable tag: `<DOCKERHUB_USER>/url-shortener-python:main-<short-sha>`

### Staging & Prod Pipelines — Build Only
- On `staging`: Builds and pushes `:stage` and `:staging-<short-sha>`. No test stages.
- On `prod`: Builds and pushes `:prod` and `:prod-<short-sha>`. No test stages.

### CircleCI Credentials
Set in CircleCI **Project Settings &rarr; Environment Variables**:
- `DOCKERHUB_USER`: Docker Hub username
- `DOCKERHUB_TOKEN`: Docker Hub Personal Access Token (PAT)

---

## 6. Git Branch Promotion Workflow

Promotion strictly follows:
$$\text{feature/<name>} \longrightarrow \text{main (QA)} \longrightarrow \text{staging} \longrightarrow \text{prod}$$

### Setting up the Protected Branch Ruleset
On GitHub: **Settings &rarr; Rules &rarr; Rulesets &rarr; New branch ruleset**:
- **Ruleset name:** `protected-branches`
- **Enforcement status:** `Active`
- **Bypass list:** *Leave completely empty*
- **Target branches:** Include by pattern &rarr; `main`, `staging`, `prod`
- **Rules to enable:**
  - [x] Restrict deletions
  - [x] Block force pushes
  - [x] Require a pull request before merging (0 approvals required for solo work)

### Promotion via Pull Requests
1. Open PR from `feature/<name>` into `main` and merge.
2. Open PR from `main` into `staging` &rarr; Merge using **"Create a merge commit"** (never Squash).
3. Open PR from `staging` into `prod` &rarr; Merge using **"Create a merge commit"** (never Squash).
4. Verify branch consistency:
   ```bash
   git diff main staging   # Must be completely empty
   git diff staging prod   # Must be completely empty
   git log --oneline --graph --all
   ```

---

## 7. Kubernetes Multi-Namespace Deployment

Kubernetes manifests are organized under `k8s/` for three isolated namespaces: `qa`, `stage`, and `prod`.

### Features
- **Namespaces:** `qa`, `stage`, `prod`
- **Automated DB Migrations:** ConfigMap mounts `.sql` migrations into PostgreSQL's `/docker-entrypoint-initdb.d/`.
- **Image Pull Secrets:** Docker registry secret `dockerhub` referenced via `imagePullSecrets`.
- **Target Images:**
  - `qa` pulls `:qa` with `imagePullPolicy: Always`
  - `stage` pulls `:stage` with `imagePullPolicy: Always`
  - `prod` pulls `:prod` with `imagePullPolicy: Always`
- **Probes:** HTTP liveness and readiness probes hitting `/health` on port 8080.

### Automated Setup
```bash
./k8s/setup-k8s.sh
```

### Live Demo Loop: Rolling Update & Digest Verification
```bash
./k8s/rollout-demo.sh
```
Or manually execute:
```bash
# 1. Trigger rollout restart
kubectl rollout restart deployment/url-shortener-app -n qa

# 2. Watch rollout complete
kubectl rollout status deployment/url-shortener-app -n qa

# 3. Verify running image
kubectl get pods -n qa -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}'

# 4. Verify Image ID digest matches pipeline push
kubectl describe pod $(kubectl get pods -n qa -l app=url-shortener-app -o jsonpath='{.items[0].metadata.name}') -n qa | grep -i "image id"
```

---

## 8. Demo Questions & Answers (10 Marks)

Be prepared to answer these core architectural questions during the demo:

### Q1: Why is this a Deployment and not a Pod?
> **Answer:** A Pod is an ephemeral, single instance with no self-healing, replication, or update management. If a standalone Pod crashes or the node fails, it is lost forever. A Deployment provides declarative state management via an underlying ReplicaSet. It guarantees high availability, automatic self-healing (recreating dead pods), zero-downtime rolling updates (`RollingUpdate` strategy), and easy rollbacks if a new version fails.

### Q2: Your integration test talks to localhost on CircleCI but to db in Compose. Why are those different?
> **Answer:** In Docker Compose, each service runs in its own network container attached to a user-defined bridge network; Compose provisions an internal DNS server that resolves service names (`postgres`, `redis`) to container IP addresses. In CircleCI, primary and secondary service containers share the same network namespace (`localhost`); all exposed ports are mapped directly to `localhost`, meaning services must be accessed via `localhost:5432` and `localhost:6379`.

### Q3: What happens if I delete one of your Pods right now?
> **Answer:** Because the Pod is managed by a Deployment controller (via its ReplicaSet), the ReplicaSet actively reconciles the actual state with the desired state (`replicas: 1`). The moment the Pod is deleted, the control loop detects `current_replicas (0) < desired_replicas (1)` and immediately provisions a new Pod to restore the desired state.

### Q4: Why does your Dockerfile create a user instead of running as root?
> **Answer:** Principle of Least Privilege and container breakout defense. Running as root inside a container means that if an attacker discovers a Remote Code Execution (RCE) vulnerability or container breakout flaw, they inherit root privileges on the underlying host kernel. Running as an unprivileged user (`appuser` with `USER appuser` and `/sbin/nologin`) confines the process to minimal filesystem and system call privileges.

### Q5: Your Service says Running but the page does not load. Where do you look first?
> **Answer:** First inspect the Service endpoints:
> ```bash
> kubectl get endpoints <service-name> -n <namespace>
> ```
> If the `ENDPOINTS` column is `<none>`, the Service's `selector` labels do not match the Pod's `metadata.labels`. If endpoints are populated, check Pod readiness status (`kubectl describe pod`) to verify health check probes aren't failing, followed by checking container port mappings (`containerPort: 8080` vs `targetPort`).

### Q6: Why :qa and :stage rather than one :latest tag for everything?
> **Answer:** `:latest` is ambiguous, mutable, and breaks environment isolation. Different environments (`qa`, `staging`, `production`) run different stages of the release lifecycle. Having environment-specific moving tags (`:qa`, `:stage`, `:prod`) ensures that each Kubernetes namespace tracks only the release certified for that tier. Furthermore, combining moving tags with immutable SHA tags (`:<branch>-<short-sha>`) guarantees auditability and reproducibility.

### Q7: What exactly does rollout restart do — does it rebuild anything?
> **Answer:** `kubectl rollout restart` does **not** rebuild the Docker image. It patches the Deployment's Pod template with an updated annotation timestamp (`kubectl.kubernetes.io/restartedAt`), which triggers the Deployment controller to perform a rolling update: pulling the latest image tag from the registry (because `imagePullPolicy: Always` is set) and launching fresh Pods while terminating old ones.
