# lavenbloom-habit-service

> **Runbook & Developer Walkthrough** — Habit tracking and health metrics microservice for the Lavenbloom platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Environment Variables](#environment-variables)
5. [Local Development Walkthrough](#local-development-walkthrough)
6. [Docker Walkthrough](#docker-walkthrough)
7. [Redis Event Queue](#redis-event-queue)
8. [CI/CD Pipeline Walkthrough](#cicd-pipeline-walkthrough)
9. [Kubernetes Deployment](#kubernetes-deployment)
10. [Secrets Management](#secrets-management)
11. [Troubleshooting](#troubleshooting)

---

## Overview

`habit-service` is a **FastAPI** microservice that manages daily habit tracking and health metrics for authenticated users. It is the core data-writing service of the Lavenbloom platform.

Key responsibilities:
- Create and retrieve user **habits**
- Log daily **habit completions** (done / not done)
- Record **health metrics** (e.g., sleep, steps, mood) per day
- **Publish missed-habit events** to a Redis queue, consumed asynchronously by `notification-service`

All routes require a valid JWT Bearer token issued by `auth-service`.

| Property | Value |
|---|---|
| **Runtime** | Python 3.11 |
| **Framework** | FastAPI |
| **Database** | PostgreSQL 15 (`habit_db`) |
| **Auth** | JWT (HS256) — verified locally |
| **Message Queue** | Redis 7 (pub/sub push to `missed_habits_queue`) |
| **Port** | `8000` |
| **Docker image** | `lavenbloom/lavenbloom-habit-service` |

---

## Architecture

```
┌──────────────┐    JWT     ┌──────────────────┐    SQLAlchemy   ┌──────────────────┐
│   Frontend   │ ─────────▶ │  habit-service   │ ──────────────▶ │  PostgreSQL       │
│  (via Gateway│            │  FastAPI :8000   │                 │  (habit_db)       │
└──────────────┘            └──────────────────┘                 └──────────────────┘
                                     │
                              redis.lpush()
                              (missed habit)
                                     │
                                     ▼
                            ┌─────────────────┐
                            │   Redis :6379    │
                            │ missed_habits_   │
                            │     queue        │
                            └────────┬────────┘
                                     │
                              consumed by
                                     ▼
                        ┌────────────────────────┐
                        │  notification-service  │
                        │  (worker thread)       │
                        └────────────────────────┘
```

### Source Layout

```
habit-service/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI routes
│   ├── auth_middleware.py  # JWT verification (get_current_user dependency)
│   ├── database.py         # SQLAlchemy engine + session
│   ├── models.py           # Habit, HabitLog, Metric ORM models
│   ├── schemas.py          # Pydantic schemas
│   └── redis_client.py     # notify_missed_habit() → Redis lpush
├── Dockerfile
├── requirements.txt
└── sonar-project.properties
```

---

## API Reference

All endpoints (except `/health`) require:
```
Authorization: Bearer <JWT_TOKEN>
```

### `GET /health`

```bash
curl http://localhost:8002/health
# {"status":"ok"}
```

---

### `POST /habits`

Create a new habit for the authenticated user.

**Request body:**
```json
{
  "name": "Morning Run",
  "description": "Run 5km every morning"
}
```

**Success — `200 OK`:**
```json
{
  "id": 1,
  "user_id": 42,
  "name": "Morning Run",
  "description": "Run 5km every morning"
}
```

---

### `GET /habits`

Retrieve all habits for the authenticated user.

```bash
curl http://localhost:8002/habits \
  -H "Authorization: Bearer <token>"
# [{"id":1,"user_id":42,"name":"Morning Run",...}]
```

---

### `POST /habits/{habit_id}/logs/{log_date}`

Log a habit completion (or update an existing log) for a given date.

**Path parameters:**
- `habit_id` — integer habit ID
- `log_date` — date in `YYYY-MM-DD` format

**Request body:**
```json
{
  "is_done": false,
  "note": "Skipped due to rain"
}
```

**Success — `200 OK`:**
```json
{
  "id": 7,
  "habit_id": 1,
  "user_id": 42,
  "date": "2025-04-28",
  "is_done": false,
  "note": "Skipped due to rain"
}
```

> When `is_done` is `false`, a missed-habit event is automatically pushed to Redis: `{ "user_id": 42, "habit_name": "Morning Run", "date": "2025-04-28" }`.

---

### `GET /habits/logs`

Retrieve all habit logs for the authenticated user.

```bash
curl http://localhost:8002/habits/logs \
  -H "Authorization: Bearer <token>"
```

---

### `POST /metrics/{log_date}`

Log or update a health metric for a given date.

**Path parameter:**
- `log_date` — date in `YYYY-MM-DD` format

**Request body:**
```json
{
  "metric_type": "sleep_hours",
  "value": 7.5
}
```

Supported `metric_type` values (by convention): `sleep_hours`, `steps`, `mood`, `water_ml`, etc.

---

### `GET /metrics`

Retrieve all metrics for the authenticated user. Optionally filter by type.

```bash
# All metrics
curl http://localhost:8002/metrics -H "Authorization: Bearer <token>"

# Filter by type
curl "http://localhost:8002/metrics?metric_type=sleep_hours" \
  -H "Authorization: Bearer <token>"
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_URI` | ✅ | `postgresql://user:password@localhost/habit_db` | PostgreSQL connection string |
| `JWT_SECRET` | ✅ | `supersecretjwtkey` | Must match the value used by `auth-service` |
| `REDIS_URI` | ✅ | `redis://localhost:6379/0` | Redis connection URI for event publishing |

---

## Local Development Walkthrough

### Prerequisites

- Python 3.11+
- PostgreSQL 15 (local or via Docker)
- Redis 7 (local or via Docker)

### Step 1 — Install dependencies

```bash
git clone https://github.com/lavenbloom/lavenbloom-habit-service.git
cd lavenbloom-habit-service
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Start dependencies (Docker shortcut)

```bash
docker run -d --name habit-db \
  -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DB=habit_db \
  -p 5433:5432 postgres:15-alpine

docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### Step 3 — Set environment variables

```bash
export POSTGRES_URI="postgresql://user:password@localhost:5433/habit_db"
export JWT_SECRET="devsecret"
export REDIS_URI="redis://localhost:6379/0"
```

### Step 4 — Run the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger docs available at `http://localhost:8000/docs`.

### Step 5 — End-to-end walkthrough

```bash
# 1. Get a token from auth-service (must be running on :8001)
TOKEN=$(curl -s -X POST http://localhost:8001/login \
  -d "username=testuser&password=pass1234" | jq -r .access_token)

# 2. Create a habit
curl -X POST http://localhost:8000/habits \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Morning Run","description":"5km daily"}'

# 3. Log it as missed
curl -X POST http://localhost:8000/habits/1/logs/2025-04-28 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_done":false,"note":"Skipped"}'

# 4. Check metrics
curl -X POST http://localhost:8000/metrics/2025-04-28 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"metric_type":"sleep_hours","value":6.5}'
```

---

## Docker Walkthrough

### Build and run standalone

```bash
docker build -t lavenbloom-habit-service:local .

docker run -d \
  -e POSTGRES_URI="postgresql://user:password@host.docker.internal:5433/habit_db" \
  -e JWT_SECRET="devsecret" \
  -e REDIS_URI="redis://host.docker.internal:6379/0" \
  -p 8002:8000 \
  lavenbloom-habit-service:local
```

### Full stack via Docker Compose

```bash
# From project root
docker compose up habit-db redis habit-service
```

Service available at `http://localhost:8002`.

---

## Redis Event Queue

When a habit is logged as `is_done: false`, `habit-service` calls `notify_missed_habit()` which performs:

```python
redis_client.lpush("missed_habits_queue", json.dumps({
    "user_id": user_id,
    "habit_name": habit_name,
    "date": date_str
}))
```

The `notification-service` worker thread runs `BRPOP missed_habits_queue` in a loop and persists each consumed event to its own `notification_logs` PostgreSQL table.

### Verify the queue manually

```bash
# Connect to Redis CLI
docker exec -it redis redis-cli

# Check queue length
LLEN missed_habits_queue

# Peek at items without consuming
LRANGE missed_habits_queue 0 -1
```

---

## CI/CD Pipeline Walkthrough

Pipeline file: `.github/workflows/ci-habit-service.yml`

| Event | Jobs triggered |
|---|---|
| Pull Request → `develop` / `main` | `sast` → `sca` → `trivy` → `pr-check` |
| Push → `develop` | `dev-publish` → `dev-cd` |
| GitHub Release created | `publish` → `cd` |

The workflow calls shared reusable workflows from `lavenbloom-shared`:
- **`ci-sast.yml`** — SonarQube static analysis
- **`ci-sca.yml`** — Snyk dependency scan (`runtime: python`)
- **`ci-docker-build.yml`** — Temp Docker build + Trivy CVE scan
- **`ci-docker-publish.yml`** — Tag as `dev-{SHA}` or semver, push to Docker Hub
- **`cd-template.yml`** — Update `values-dev.yaml` or `values-prod.yaml` in `lavenbloom-charts`

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `SONAR_TOKEN` | SonarQube token |
| `SONAR_URL` | SonarQube URL |
| `SNYK_TOKEN` | Snyk API token |
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PASSWORD` | Docker Hub password/token |
| `HELM_REPO_PAT` | PAT for `lavenbloom-charts` repo push access |

---

## Kubernetes Deployment

`habit-service` runs in the `backend` namespace. Its PostgreSQL StatefulSet and Redis are separate resources.

### Verify deployment

```bash
kubectl get pods -n backend -l app=habit-service
kubectl logs -n backend deployment/habit-service

# Port-forward for local testing
kubectl port-forward -n backend deployment/habit-service 8002:8000
```

### Check secrets

```bash
kubectl get secret habit-service-secret -n backend -o jsonpath='{.data.REDIS_URI}' | base64 -d
kubectl get secret habit-service-secret -n backend -o jsonpath='{.data.JWT_SECRET}' | base64 -d
```

### Network policy

- `habit-service` → `habit-db` (PostgreSQL in `db` namespace): **allowed**
- `habit-service` → `redis` (in `backend` namespace): **allowed**
- All other cross-service traffic: **denied**

---

## Secrets Management

| Secret Name (K8s) | Keys | Notes |
|---|---|---|
| `habit-service-secret` | `POSTGRES_URI`, `JWT_SECRET`, `REDIS_URI` | Injected via `envFrom.secretRef` |
| `habit-db-secret` | `POSTGRES_USER`, `POSTGRES_PASSWORD` | Used by the PostgreSQL StatefulSet |

---

## Troubleshooting

### `403 Forbidden` on all habit routes

The JWT token is either expired (lifetime: 60 min) or the `JWT_SECRET` in `habit-service-secret` does not match the one used by `auth-service`. Re-login to get a fresh token and confirm both secrets are identical.

### Redis connection refused

Verify the `REDIS_URI` environment variable points to the correct Redis host/port. In Kubernetes, Redis runs as a ClusterIP service in the `backend` namespace; the URI should be `redis://redis:6379/0`.

### Missed-habit events not appearing in notification logs

Check that `notification-service` is running and its worker thread started successfully:

```bash
kubectl logs -n backend deployment/notification-service | grep -i worker
kubectl logs -n backend deployment/notification-worker
```

Also verify Redis connectivity from both services.

### `404 Not Found` on `/habits/{habit_id}/logs/{date}`

The habit must belong to the authenticated user. Double-check `habit_id` from `GET /habits` and that you are using the token for the same user who created the habit.