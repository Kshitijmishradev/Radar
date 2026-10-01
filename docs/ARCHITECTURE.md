# Architecture

Radar Remediation Engine is a local-first cost-remediation control plane. It accepts a cost anomaly, applies deterministic safety policy, waits for the right human approval, then sends an approved action through a durable worker queue.

```text
Cost anomaly source
        |
        v
FastAPI ingestion API
        |
        +--> SQLite: anomaly, action, audit record
        |
        v
Approval workflow
        |
        v
SQLite durable job queue
        |
        v
Worker process
        |
        v
Simulated cloud adapter

Browser dashboard <-- SSE events <-- API process
```

## Safety boundaries

- Policies only propose action for owned, opted-in, idle non-production EC2 resources.
- Production resources are ineligible.
- Approval and execution are separate durable states.
- A job is claimed atomically and can only execute once.
- Every state change creates an audit record.
- Sessions are signed and every REST/SSE query is scoped to one tenant.

## Local versus deployed components

| Local prototype | Production replacement |
|---|---|
| SQLite | PostgreSQL |
| In-process SSE broker | Redis Pub/Sub or managed event bus |
| SQLite job queue | SQS, Redis Streams, or another durable queue |
| Signed demo cookie | OIDC / enterprise SSO |
| Simulated adapter | least-privilege, tenant-scoped AWS adapter |

The interfaces are deliberately separated so these replacements do not alter the dashboard flow or business workflow.
