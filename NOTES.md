# habit-service — Study Notes

---

## Table of Contents

1. [How This Service Works](#1-how-this-service-works)
2. [Docker Basics](#2-docker-basics)
3. [Dockerfile — Line by Line](#3-dockerfile--line-by-line)
4. [Q&A](#4-qa)

---

## 1. How This Service Works

### What it does

The habit-service manages the core product feature: **habit tracking**. Users create habits (e.g., "meditate 20 minutes") and log completions. It also tracks health metrics (mood, energy, sleep) and sends missed-habit events to notification-service via Redis.

### API routes

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Health check for Kubernetes |
| `POST` | `/habits` | Create a new habit for the authenticated user |
| `GET` | `/habits` | List all habits for the authenticated user |
| `POST` | `/habits/{habit_id}/log` | Log a habit completion; pushes Redis event if missed |
| `POST` | `/health-metrics` | Log a health metric entry (mood, energy, sleep) |
| `GET` | `/health-metrics` | Get all health metric entries for the user |

### Authentication

Every route except `/health` requires a JWT in the `Authorization: Bearer <token>` header. `auth_middleware.py` verifies the token using `JWT_SECRET` (same secret as auth-service). If valid, it extracts the `user_id` from the token payload and uses it in all database queries — users only see their own data.

### The Redis event system

When a habit completion is logged and a prior completion was missed, the service pushes a JSON message onto a Redis list:

```python
redis_client.rpush(
    "missed_habits",
    json.dumps({"user_id": user_id, "habit_name": habit.name, "missed_at": "..."})
)
```

`rpush` appends to the **right end** of the `missed_habits` list. The notification-service worker reads from the **left end** with `blpop` (blocking pop) — this creates a **first-in, first-out queue**. The two services never call each other directly. This is **event-driven architecture**: services communicate through a shared queue, not HTTP. If notification-service is down, messages accumulate in Redis and are processed when it recovers.

### Database

PostgreSQL (`habit_db`) with tables for habits, habit_logs, and health_metrics. All queries filter by `user_id` extracted from the JWT.

### Component connections

```
User → Gateway → /habit/* → habit-service:8000 → PostgreSQL habit-db:5432
                                   ↓ rpush
                              Redis:6379 (missed_habits queue)
                                   ↓ blpop
                         notification-service background worker
```

---

## 2. Docker Basics

### Image layers and caching

```
Layer 0: python:3.11-slim         ← Base image (from registry, shared, rarely changes)
Layer 1: apt-get install gcc      ← Only rebuilds if the RUN command changes
Layer 2: pip install requirements ← Only rebuilds if requirements.txt changes
Layer 3: COPY app/                ← Rebuilds on every code change
Layer 4: useradd + chown          ← Rebuilds when layer 3 rebuilds
```

**Rule:** Put the things that change least at the top of the Dockerfile.

### Environment variables in Docker

```bash
# Passed at runtime — never baked into the image
docker run -e POSTGRES_URI="postgresql://..." -e JWT_SECRET="..." habit-service:latest
```

In Kubernetes, these come from a `Secret` via `envFrom.secretRef` in the Deployment manifest. The image itself contains no credentials — only the running container does.

### Container networking

In Docker Compose, containers reach each other by service name (`redis://redis:6379`). In Kubernetes, the same pattern works via Service DNS: `redis.backend.svc.cluster.local:6379`. The application code uses environment variables for hostnames — never hardcoded IPs.

---

## 3. Dockerfile — Line by Line

```dockerfile
FROM python:3.11-slim
```
**Base image.** Debian-based, Python 3.11 pre-installed. `slim` removes documentation and non-essential packages. Chosen over `alpine` because `psycopg2` requires `glibc` (present in Debian/slim, absent in Alpine's `musl libc`).

---

```dockerfile
WORKDIR /app
```
**Sets the working directory** for all subsequent instructions. Creates `/app` if it doesn't exist. All relative paths in later `COPY` and `RUN` instructions are relative to `/app`.

---

```dockerfile
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```
**Installs OS-level build tools:**
- `gcc` — C compiler. Required to build `psycopg2` from source (it's a C extension)
- `libpq-dev` — PostgreSQL development headers. `psycopg2` links against these at compile time

**`&& rm -rf /var/lib/apt/lists/*`** — Removes the apt package list cache downloaded by `apt-get update`. Must be in the **same `RUN` layer** as the install. If put in a separate `RUN`, Docker's layer caching stores the cache in a prior immutable layer, wasting space in the final image.

---

```dockerfile
COPY requirements.txt .
```
**Copies only `requirements.txt` first** — before the application code. This exploits Docker's layer cache: if `requirements.txt` hasn't changed (dependencies didn't change), Docker skips the `pip install` step entirely on subsequent builds, even if `app/*.py` files changed.

---

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```
**Installs all Python packages.** Key packages for this service:
- `fastapi` + `uvicorn` — web framework and ASGI server
- `sqlalchemy` + `psycopg2-binary` — ORM + PostgreSQL driver
- `python-jose` — JWT verification (shares `JWT_SECRET` with auth-service)
- `redis` — Python Redis client. `rpush`/`blpop` calls in `main.py` use this library

`--no-cache-dir` — pip normally stores downloaded wheels in `~/.cache/pip`. In a Docker build, this cache is discarded when the build finishes, so storing it wastes layer space.

---

```dockerfile
COPY app/ app/
```
**Copies application source code** (`main.py`, `database.py`, `auth_middleware.py`) to `/app/app/`. Placed after `pip install` so code changes don't invalidate the dependency layer.

---

```dockerfile
RUN useradd -m appuser && chown -R appuser /app
USER appuser
```
**Non-root security hardening:**
- `useradd -m appuser` — creates system user `appuser` with a home directory
- `chown -R appuser /app` — transfers ownership of the entire `/app` directory
- `USER appuser` — all subsequent operations and the running container use `appuser`

Without this, the container runs as `root`. A compromised process running as root has write access to the entire container filesystem and potential container-escape vectors. `appuser` has no such privileges.

---

```dockerfile
EXPOSE 8000
```
**Metadata declaration** that this container listens on port 8000. Does not open any ports — that is done by Kubernetes Service or `docker run -p`. Serves as documentation for operators and tooling.

---

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
**Default startup command** in JSON array (exec) form — runs `uvicorn` directly, not through a shell:
- `app.main:app` — `app/main.py` module, `app` variable (the FastAPI instance)
- `--host 0.0.0.0` — bind to all network interfaces. Without this, the service only accepts loopback connections (`127.0.0.1`) — invisible to Kubernetes networking
- `--port 8000` — matches `EXPOSE` and the Kubernetes Service `targetPort`

Exec form (`["uvicorn", ...]`) ensures `SIGTERM` from `docker stop` reaches the uvicorn process directly for graceful shutdown.

---

## 4. Q&A

**Q: Why does habit-service need the same `JWT_SECRET` as auth-service?**
A: The `JWT_SECRET` is the HMAC signing key. auth-service signs the token with it. habit-service verifies the token's signature with the same key. If they used different secrets, all tokens would fail verification in habit-service. In Kubernetes, the same secret value is sealed into both services' SealedSecret resources.

**Q: What happens if Redis is down when habit-service tries to `rpush`?**
A: The `rpush` call would raise a `redis.ConnectionError`. The application would return a 500 error for that request. The habit log itself might still be saved in PostgreSQL (depending on where in the request handler the error occurs). The notification event is lost. For production resilience, you'd add a retry mechanism or write the event to a local dead-letter queue.

**Q: Why is `psycopg2-binary` used in `requirements.txt` instead of `psycopg2`?**
A: `psycopg2-binary` is a pre-compiled wheel that bundles the `libpq` library inside it. It installs without needing `gcc` or `libpq-dev`. If `psycopg2-binary` was used, the `apt-get install gcc libpq-dev` step would be unnecessary. The Dockerfile installs build tools anyway — this might be because `psycopg2` (without `-binary`) is intended to be used, or it's left as a safety net for other packages that might need a compiler.

**Q: What is the difference between `rpush` and `lpush` in Redis?**
A: `rpush` appends to the **right** end of the list. `lpush` prepends to the **left** end. `blpop` reads from the **left** end. So `rpush` + `blpop` = FIFO queue (first message in, first message processed). `lpush` + `blpop` = LIFO stack. This service uses FIFO so older missed-habit notifications are processed before newer ones.
