# AWS Deployment Plan

Companion to [`01-PROJECT-DEEP-DIVE.md`](./01-PROJECT-DEEP-DIVE.md) and [`02-DOCKER-CICD.md`](./02-DOCKER-CICD.md). This is a deployment **plan**, not yet applied infrastructure — nothing in this repo provisions AWS resources today. It maps each of the three already-containerized services onto managed AWS primitives, favoring the option that needs the least babysitting for a project at this scale.

## Target architecture

```
                              Route 53 (lumen.example.com)
                                        │
                                        ▼
                          ACM cert  ─►  Application Load Balancer
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
            /*  → frontend TG    /api/* → backend TG   (agent has no
            (ECS Fargate,        (ECS Fargate)           public route —
             nginx:8081)              │                  backend-only)
                                       ▼
                              research-agent TG
                              (ECS Fargate, private)
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                                      ▼
              RDS Postgres 16                        ElastiCache Redis 7
              (Multi-AZ, private subnet)              (private subnet)
```

All three services already run as Docker containers with health-check endpoints (`/health` on backend, `/health/ready` on the agent, `/healthz` on the new frontend nginx image) — that's exactly what ECS Fargate target-group health checks need, so no re-architecture is required to deploy this on AWS, only infrastructure and pipeline wiring.

## Why Fargate over the alternatives

| Option | Verdict |
|---|---|
| **ECS on Fargate** (recommended) | No EC2 fleet to patch/scale; pay per task; matches "3 independently-scalable stateless containers" exactly. Chosen. |
| App Runner | Simpler still, but one service per app and weaker control over networking (VPC connector needed for private RDS/Redis access) — worth reconsidering only if the team wants zero infra management and is fine paying the VPC-connector latency tax. |
| EKS | Overkill for 3 services and a small team — real value only once there are many more services or a hard Kubernetes requirement. |
| EC2 + docker compose | Closest to what already runs locally, but reintroduces exactly the patching/scaling/failover work Fargate removes. Only worth it to keep costs near-zero on a single small instance for a portfolio demo. |

## Step by step

### 1. Networking

- One VPC, 2 AZs minimum (Multi-AZ RDS requires it).
- Public subnets: ALB only.
- Private subnets: ECS tasks, RDS, ElastiCache. Nothing in a private subnet gets a public IP; egress (for OpenRouter, Octen, Tavily, Jina, market-data APIs) goes through a NAT Gateway.
- Security groups: ALB → frontend/backend tasks on their container ports only; backend task SG → research-agent task SG on 8004 only; backend task SG → RDS SG on 5432 only; research-agent task SG → ElastiCache SG on 6379 only. No service reaches a datastore it doesn't own — the agent never gets a security-group path to Postgres.

### 2. Data layer

- **RDS for PostgreSQL 16**, Multi-AZ, `db.t4g.micro`/`small` to start (matches the `postgres:16-alpine` image used locally). Automated backups on, 7-day retention minimum.
- **ElastiCache for Redis 7**, single node to start (it's a cache, not source of truth — losing it just means cold tool caches, not data loss) — one `cache.t4g.micro` node is plenty at this traffic.
- Before first deploy: run `Base.metadata.create_all` once against RDS the same way the backend does locally, or — better — this is the moment to finally wire up **Alembic** (already a dependency, unused today per the deep-dive doc's "known gaps") so schema changes ship as reviewable migrations instead of implicit `create_all` diffing.

### 3. Secrets

**Everything currently in `backend/.env` / `research-agent/.env` moves to AWS Secrets Manager** — `JWT_SECRET`, `OPENROUTER_API_KEY`, `OCTEN_API_KEY`, `TAVILY_API_KEY`, `DATABASE_URL` (or its components), and the OpenAI fallback key if set. ECS task definitions reference these via `secrets:` (resolved by the ECS agent at container start, injected as env vars — the app code needs zero changes, `pydantic-settings` already just reads env vars). Never bake these into the Docker image or commit them to the repo — the same rule the local `.env` files already follow via `.gitignore`.

### 4. Container images

Push the three images built in [`02-DOCKER-CICD.md`](./02-DOCKER-CICD.md) to three ECR repositories: `lumen-frontend`, `lumen-backend`, `lumen-research-agent`. Enable ECR image scanning on push (free vulnerability scanning, catches CVEs in `python:3.12-slim`/`node:20-slim`/`nginx:1.27-alpine` base layers before they reach a running task).

### 5. ECS services

Three services in one cluster (`lumen`), each with its own task definition:

| Service | Container port | CPU / Memory (start) | Desired count | Target group health check |
|---|---|---|---|---|
| `frontend` | 8081 | 0.25 vCPU / 512 MB | 2 | `GET /healthz` |
| `backend` | 8080 | 0.5 vCPU / 1 GB | 2 | `GET /health` |
| `research-agent` | 8004 | 0.5 vCPU / 1 GB | 2 | `GET /health/ready` |

`desired count: 2` minimum for every service from day one — a single-task service has no rolling-deploy safety net and no AZ redundancy. Attach an **Application Auto Scaling** target-tracking policy per service on ECS service CPU utilization (scale out above ~65%) — the research-agent is the one most likely to need it, since a slow upstream LLM/search call ties up a task for the duration of the request.

`research-agent`'s target group is **not** attached to any ALB listener rule — it's only reachable from the backend's security group, matching how it behaves today (no auth of its own; the backend is its only intended caller).

### 6. Load balancer & routing

One internet-facing ALB, one HTTPS listener (443, ACM-issued cert for the domain), HTTP (80) listener that just redirects to HTTPS. Listener rules:

- `path-pattern: /api/*` → backend target group
- default (everything else) → frontend target group

This is exactly why `VITE_API_URL` is left unset in the production build ([`02-DOCKER-CICD.md`](./02-DOCKER-CICD.md)) — frontend and backend share one origin behind the ALB, so the browser's `/api/*` calls just work with no CORS configuration needed. Set `CORS_ALLOWED_ORIGINS` on the backend to the production domain anyway, as defense in depth against the API being called from an unexpected origin.

### 7. DNS & TLS

Route 53 hosted zone for the domain, `A`/`AliasTarget` record → the ALB. ACM certificate (DNS-validated via Route 53) attached to the HTTPS listener — free, auto-renewing, no cert rotation to manage.

### 8. Observability

- **CloudWatch Logs**: each ECS task definition's `logConfiguration` ships stdout/stderr to a log group per service (`/ecs/lumen-backend`, etc.) — no code changes needed, both Python services already log to stdout (`coloredlogs`/`logging.basicConfig`).
- **CloudWatch Container Insights**: enable on the cluster for CPU/memory/network dashboards per service without instrumenting anything.
- **`/metrics`**: `research-agent` already exposes Prometheus metrics via `prometheus-fastapi-instrumentator`. If/when there's a Prometheus + Grafana stack (self-hosted on ECS, or Amazon Managed Prometheus/Grafana), this is a scrape target for free — no code change required, just wiring.
- **Alarms**: CloudWatch alarms on each target group's `UnHealthyHostCount` and ALB `5XXCount`, notifying an SNS topic (email/Slack webhook).

### 9. CI/CD wiring

Ties directly to the GitHub Actions workflows in [`02-DOCKER-CICD.md`](./02-DOCKER-CICD.md): the per-service build workflow pushes `:${{ github.sha }}` and `:latest` to ECR; the `deploy.yml` workflow calls `aws ecs update-service --force-new-deployment` for the matching service, using an OIDC-federated GitHub Actions role scoped to exactly `ecr:PutImage` (build jobs) and `ecs:UpdateService` (deploy job) on this cluster's ARNs — not a general admin role.

## Rollout order

1. VPC, subnets, security groups, NAT.
2. RDS + ElastiCache (data layer first — nothing else can start meaningfully without it).
3. Secrets Manager entries.
4. ECR repos + first manual image push (validates the Dockerfiles build and run before any automation depends on them).
5. ECS cluster + all three task definitions/services, `desired count: 0` initially.
6. ALB + target groups + listener rules, then scale services to their real desired count and confirm health checks go green.
7. Route 53 + ACM, cut DNS over.
8. Wire the GitHub Actions workflows and OIDC role; confirm a no-op deploy (build + `update-service --force-new-deployment`) round-trips cleanly before relying on it for real changes.

## Cost shape (rough, us-east-1, minimum viable sizing above)

- ECS Fargate: 3 services × 2 tasks × ~0.5 vCPU/1GB avg ≈ the dominant recurring cost, scales with traffic.
- RDS `db.t4g.micro` Multi-AZ + ElastiCache `cache.t4g.micro`: modest, roughly comparable to one Fargate service.
- ALB: fixed hourly charge + LCU usage, small at this scale.
- NAT Gateway: often the surprise line item on a low-traffic project — its hourly charge plus per-GB egress can rival the compute cost. Worth revisiting (VPC endpoints for AWS APIs, or accepting public subnets for the agent's outbound-only calls) if cost becomes a concern before traffic justifies the NAT.

None of this is provisioned yet — this doc is the plan to hand to Terraform/CDK/the console when it's time to actually stand it up.
