# Docker & CI/CD

Companion to [`01-PROJECT-DEEP-DIVE.md`](./01-PROJECT-DEEP-DIVE.md). Covers how the three services are containerized today, what changed to make the frontend deployable the same way, and a GitHub Actions pipeline to build/test/push all three.

## Containerization, service by service

### `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim
...
RUN apt-get install -y build-essential libpq5   # libpq5 = runtime dep for psycopg[binary]
COPY requirements.txt . && RUN pip install -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
```

Single-stage, pinned dependency versions (`requirements.txt` uses `==`, not `>=`), `--proxy-headers` so Uvicorn trusts `X-Forwarded-For`/`X-Forwarded-Proto` from whatever sits in front of it (ALB in prod, `docker compose` locally has no proxy so this is a no-op there).

### `research-agent/Dockerfile`

```dockerfile
FROM python:3.12-slim
...
COPY pyproject.toml README.md . && COPY src/ src/
RUN pip install .
CMD ["uvicorn", "research_agent.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8004"]
```

`--factory` because `server.py` exposes `create_app()` rather than a module-level `app` — the factory builds the FastAPI app inside the `lifespan` context manager that opens/closes the Redis connection pool.

### `frontend/Dockerfile` — **new, added alongside this doc**

The frontend previously only ran via `npm run dev` (Vite's dev server) — fine for local development, not a deployable artifact. It's now a **two-stage build**:

```dockerfile
FROM node:20-slim AS build
...
ARG VITE_API_URL
RUN npm run build          # tsc -b && vite build → static dist/

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8081
```

Two things worth knowing:

1. **`VITE_API_URL` is a *build-time* ARG, not a runtime env var.** Vite inlines `import.meta.env.*` into the JS bundle at build time — there's no server process to read an env var from at container start. Left unset, the app calls same-origin `/api/*` (see `lib/api.ts`/`lib/sse.ts` defaults), which is exactly right when an ALB/ingress routes `/api/*` to the backend and everything else to this container — no CORS, no separate domain. Only set `VITE_API_URL` at build time if frontend and backend are intentionally on different origins.
2. **`nginx.conf`'s `try_files $uri $uri/ /index.html`** is the SPA fallback — without it, a hard refresh on `/app/c/<uuid>` 404s, because nginx has no idea `react-router` owns that path client-side.

`frontend/nginx.conf` listens on `8081` (not the nginx default `80`) so it can run as a non-root container user without needing `CAP_NET_BIND_SERVICE` for a privileged port — matters for the AWS/ECS deployment in the next doc, where tasks should not run as root.

## `docker-compose.yml` — local dev orchestration

```yaml
services:
  postgres:   # 16-alpine, host port 5433 (avoids clashing with a local Postgres install)
  redis:      # 7-alpine, host port 6379
  research-agent:  # env_file: research-agent/.env — this is where OPENROUTER_API_KEY / OCTEN_API_KEY live
  backend:    # DATABASE_URL / RESEARCH_AGENT_URL point at the other containers by service name
```

Both app services declare `depends_on` with `condition: service_healthy` (postgres, redis) or `service_started` (research-agent from backend) — Compose won't start `backend` until `postgres` passes its `pg_isready` healthcheck, avoiding the classic "backend crash-loops until Postgres is ready" race.

The frontend is **intentionally not in `docker-compose.yml`** — local development wants Vite's dev server (instant HMR), not a from-scratch container rebuild on every save. The new `frontend/Dockerfile` exists for CI and deployment, not `docker compose up`.

## Recommended CI/CD: GitHub Actions

There's no CI configured in this repo yet (no `.github/workflows/`). Given the three independently-deployable services, one workflow per service — triggered on changes to that service's path — keeps a frontend-only PR from rebuilding two Python images it didn't touch:

```yaml
# .github/workflows/backend.yml
name: backend
on:
  pull_request:
    paths: ["backend/**"]
  push:
    branches: [main]
    paths: ["backend/**"]

jobs:
  test-and-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r backend/requirements.txt
      - run: pip install pytest  # once tests exist — see gap below
      - run: cd backend && python -c "import app.main"  # smoke import, minimum viable CI today

      - if: github.ref == 'refs/heads/main'
        uses: docker/build-push-action@v6
        with:
          context: backend
          push: true
          tags: |
            ${{ vars.ECR_REGISTRY }}/lumen-backend:${{ github.sha }}
            ${{ vars.ECR_REGISTRY }}/lumen-backend:latest
```

Mirror this as `research-agent.yml` (`paths: ["research-agent/**"]`, `pip install .`) and `frontend.yml` (`paths: ["frontend/**"]`, `npm ci && npm run lint && npm run build`, then `docker/build-push-action` with `build-args: VITE_API_URL=`). Each pushes to its own ECR repository (`lumen-backend`, `lumen-research-agent`, `lumen-frontend`) tagged both `:${{ github.sha }}` (immutable, for rollback) and `:latest` (convenience).

**Auth to AWS** should use OIDC federation (`aws-actions/configure-aws-credentials` with `role-to-assume`), not long-lived `AWS_ACCESS_KEY_ID` secrets — no credential to rotate or leak.

A fourth workflow, `deploy.yml`, triggered `on: workflow_run` of any of the three build workflows completing successfully on `main`, updates the corresponding ECS service:

```yaml
- run: |
    aws ecs update-service \
      --cluster lumen \
      --service ${{ matrix.service }} \
      --force-new-deployment
```

ECS pulls `:latest` from ECR and performs a rolling deployment against the target group's health check (see [`03-AWS-DEPLOYMENT.md`](./03-AWS-DEPLOYMENT.md)) — old tasks only drain once new ones pass health checks, so a bad build doesn't take the service down.

### Current gap: no test suite

Neither `backend/` nor `research-agent/` has a `tests/` directory today (the research-agent's `pyproject.toml` has `pytest`/`pytest-asyncio`/`pytest-cov` wired into `[tool.pytest.ini_options]` and `[dependency-groups] dev`, but no tests exist yet to run). Until then, the CI steps above are intentionally scoped to "does it import / does it build" — real test coverage is the next investment before this pipeline is trustworthy enough to auto-deploy on every merge without a human in the loop.
