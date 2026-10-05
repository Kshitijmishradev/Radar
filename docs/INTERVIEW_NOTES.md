# Radar interview notes

## One-sentence description

Radar is a FinOps control plane that turns cloud and AI cost signals into
explainable, approval-gated, auditable decisions.

## Backend decisions worth highlighting

### Why policy is deterministic

Cost-control actions should be explainable. The cloud policy is a short set of
explicit checks—resource type, non-production environment, owner, opt-in, idle
duration, and cost threshold. AI budget decisions use stored spend plus a
deterministic estimate. An LLM can help analyze an incident, but it should not
be the final authority for a money-affecting remediation.

### Why approval and execution are separate

An approval changes business state; execution is asynchronous work. Radar records
the approval, creates one durable job, then lets a worker process it separately.
That makes the workflow resilient to a slow cloud API or an API-server restart.

### Why idempotency matters

Users retry and providers retry. The action queue allows only one execution job
per action. AI usage accepts a caller request ID and returns the original event
on a retry, so a network timeout cannot double-count cost.

### Why SSE is used

Cost actions are infrequent but important, so one-way live updates are simpler
than polling. The local event broker makes the behavior visible in the prototype.
At scale, Redis Pub/Sub or a managed event bus lets any API instance reach the
instance holding the browser’s SSE connection.

### Why model fallback is explicit

A lower-cost model can affect quality, latency, or safety. Radar recommends a
pre-approved fallback but never silently chooses one. The application remains
responsible for accepting that tradeoff.

### Why self-hosted models still need FinOps

Ollama may not produce a token invoice, but the GPU/server still has an hourly
cost. Radar allocates capacity cost from real runtime and configured concurrency,
which makes self-hosted model economics visible beside provider-model costs.

## Honest boundaries

- Cloud execution is simulated; the app does not reach an AWS account.
- Demo sessions are local signed cookies, not company SSO.
- SQLite and the in-process event broker are local-prototype choices.
- GPU rental replay uses a market lease rate against local measured work. It is
  not a hosted-GPU performance benchmark.

## Production replacement map

| Prototype | Production replacement |
| --- | --- |
| Signed demo session | OIDC / enterprise SSO |
| SQLite | PostgreSQL with backups |
| Local worker queue | SQS or another managed durable queue |
| In-process event broker | Redis Pub/Sub or managed event bus |
| Simulated cloud adapter | Least-privilege, tenant-scoped IAM adapter |
| Direct local Ollama | Authenticated AI gateway, SDK, or sidecar |
