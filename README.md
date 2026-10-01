# Radar Remediation Engine

Radar is a dashboard that helps a company understand, control, and reduce two fast-growing costs:

1. **Cloud infrastructure** — for example, a server that is running but no one is using.
2. **AI usage** — for example, an application making expensive model calls or renting a GPU to run its own model.

It is a portfolio prototype inspired by the FinOps (cloud financial operations) workflow: spot an unusual cost, check it against clear rules, ask the right person for approval, and keep a record of what happened.

## Start here — no technical background required

Imagine a company notices that its cloud bill suddenly rises, or that its AI assistant is becoming expensive to run. Radar answers four practical questions:

| Question | What Radar does |
| --- | --- |
| **What is costing us money?** | Shows unusual cloud spend and the cost of individual AI requests in one place. |
| **Is it safe to act?** | Checks simple safety rules. For example, it will never propose automatically stopping a production system. |
| **Who has to approve it?** | Sends a suggested action through an approval step rather than changing anything immediately. |
| **Can we explain the decision later?** | Keeps a timestamped history of the alert, decision, approver, action, and rollback. |

### What you can see in the dashboard

- **Cloud Control (`/`)**: a cost anomaly is assessed against policy. A safe, non-production resource can be proposed for shutdown; production resources and unsafe cases are rejected with an explanation. An approved action can be simulated and then rolled back.
- **Radar AI (`/ai`)**: each model request is attributed to an application, customer, and end user. The dashboard shows spend by model and customer, checks budgets *before* a request is made, and can offer an explicit lower-cost model option when a request would exceed budget.
- **Self-hosted AI / GPU view**: when a company runs a model itself with Ollama, Radar records the real tokens and runtime. It can replay that measured work against a market GPU rental rate, making the cost of operating a model visible even when the model software itself is free.

### The story this project demonstrates

> A team receives a cost signal. Radar evaluates it using defined safety and budget rules. If action is appropriate, a human approves it. The system records the outcome and immediately updates the dashboard. For AI, the same idea happens before a costly model request is sent.

### What this is—and what it is not

This is a working local prototype designed to demonstrate backend engineering decisions: secure tenant separation, role-based controls, approval workflows, reliable background work, real-time dashboard updates, cost policy evaluation, and audit history.

It does **not** connect to a real AWS account or rent a cloud GPU. Cloud changes are simulated so the demo is safe. The GPU-rental screen uses a named public market rate with real local model telemetry; it is a cost replay, not a benchmark of local hardware against that GPU.

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

## Application AI cost control (technical detail)

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

### Live Ollama telemetry test

If [Ollama](https://ollama.com/) is running locally, Radar AI can call it and
record the response's actual input tokens, output tokens, cache count, and
duration. For a self-hosted model, the cost is allocated from the machine's
hourly capacity cost rather than a provider token price.

```bash
ollama pull llama3.2:3b
OLLAMA_HOURLY_CAPACITY_COST=1.20 make run
```

Open `/ai` and select **Run Ollama request**. `OLLAMA_HOURLY_CAPACITY_COST`
should be the hourly price of the deployed CPU/GPU node; it defaults to `$1.20`
for the local demo. Configure `OLLAMA_EFFECTIVE_CONCURRENCY` when one node
serves multiple requests concurrently.

### GPU rental workload replay

**Run 3-step RTX 4090 replay** on `/ai` executes a real three-step, iterative
Ollama workload (risk analysis, plan, and critique), records each inference,
and prices its measured runtime using a named market profile: Runpod RTX 4090
Secure Cloud at `$0.74/hour` (checked 2026-10-01). This is a **lease-rate cost
replay**, not an RTX 4090 benchmark: the model runs locally, so the measured
duration is multiplied by the GPU lease rate only to make cost exposure
concrete. For a real performance-and-cost measurement, run the adapter against
an Ollama server hosted on the rented GPU by setting `OLLAMA_BASE_URL`.

## Test

```bash
python3 -m unittest discover -s tests -v
```

After creating the virtual environment, `make test` runs the same suite.
