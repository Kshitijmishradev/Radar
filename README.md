# Radar Remediation Engine

A deterministic, local-first FinOps remediation control plane.

It receives a cost anomaly, evaluates explicit policy rules, creates an approval-gated remediation action, simulates a cloud change, and retains an immutable audit trail. The initial workflow covers stopping an idle, non-production EC2 instance and starting it again as a rollback.

## Safety model

- Production resources never receive an automatic action.
- An owner, environment, and approved policy match are required before an action is proposed.
- Every action begins in `PENDING_APPROVAL`.
- Execution is idempotent: an action cannot be executed twice.
- All state transitions are appended to the audit trail.
- The included cloud adapter is a simulation; it cannot change a real AWS account.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.
Open `http://127.0.0.1:8000/` for the dashboard. Sign in through the local demo panel; it scopes all data and SSE events to the selected tenant and only exposes controls allowed by the selected role.

The dashboard listens to `GET /v1/events` with Server-Sent Events (SSE), so actions and newly received anomalies appear without a manual refresh. The local broker is intentionally in-process; a multi-instance deployment should replace it with Redis Pub/Sub or a managed event bus while keeping the same SSE endpoint.

Approved actions are now written to a durable SQLite-backed job queue. The development API starts a local worker automatically; it claims queued jobs and executes the simulated cloud action outside the approval request. To experiment with the API and worker as separate local processes, use two terminals:

```bash
RUN_LOCAL_WORKER=false .venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m app.worker
```

## Containers

```bash
cp .env.example .env
docker compose up --build
```

This starts separate API and worker containers. See [architecture notes](docs/ARCHITECTURE.md) and the [deployment guide](docs/DEPLOYMENT.md) for the current local/production boundary.

## Project boundary

This repository is a complete, portfolio-ready local prototype. Its current cloud action is intentionally simulated and its deployment artifacts stop before creating real cloud infrastructure. See [project status](PROJECT_STATUS.md) for the production replacement plan and the boundaries that require an AWS account and explicit deployment authority.

## Demonstration

Sign in through the dashboard first, then create a qualifying anomaly through the API documentation or a signed session.

```bash
curl -X POST http://127.0.0.1:8000/v1/anomalies \
  -H 'content-type: application/json' \
  -d '{
    "tenant_id": "acme-health",
    "resource_id": "i-demo-001",
    "resource_type": "ec2",
    "environment": "nonprod",
    "owner": "data-platform",
    "auto_stop": true,
    "idle_hours": 96,
    "current_daily_cost": 380,
    "expected_daily_cost": 45
  }'
```

Use the returned `action_id` to approve, execute, inspect the audit trail, and roll back:

```bash
curl -X POST http://127.0.0.1:8000/v1/actions/ACTION_ID/approve
curl -X POST http://127.0.0.1:8000/v1/actions/ACTION_ID/execute
curl http://127.0.0.1:8000/v1/actions/ACTION_ID/audit
curl -X POST http://127.0.0.1:8000/v1/actions/ACTION_ID/rollback
```

## Test

## Recording-ready dashboard demo

Load a clean, repeatable tenant with one eligible remediation and seven rejected
policy cases:

```bash
.venv/bin/python -m scripts.seed_video_demo
make run
```

Open `http://127.0.0.1:8000`, then choose **Video Demo** and **Admin**. The
dashboard shows the complete anomaly history and the reason behind every policy
verdict. It is safe to run the seed command again; it resets only the
`demo-video` tenant.

## Application AI cost control

Radar AI is a second, application-AI control surface at `http://127.0.0.1:8000/ai`.
It demonstrates the product direction beyond cloud resources: request-level model
costing, attribution to an app/customer/end user, app budgets, and a deterministic
`ALLOW` / `WARN` / `BLOCK` preflight guardrail.

When a request does not fit its budget, the demo can also offer an explicitly
approved lower-cost route (`GPT-4o → GPT-4o mini` or `Claude Sonnet → Claude
Haiku`). The caller must opt into that route; Radar AI never changes model
quality silently.

```bash
.venv/bin/python -m scripts.seed_ai_demo
make run
```

The seed creates a `demo-video` application-AI dataset. It uses a local,
versioned demonstration price catalog; it does not call an AI provider or claim
to use live provider prices.

## Test

```bash
python3 -m unittest discover -s tests -v
```

After creating the virtual environment, `make test` runs the same suite.
