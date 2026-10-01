# Project status

## Completed

- Deterministic policy evaluation for idle non-production EC2 workloads.
- Human approval, rejection, queued execution, simulated stop, and rollback workflows.
- Durable local queue with atomic worker claim and retry limit.
- Immutable-style action audit history and savings estimate.
- Dashboard with action details, role-aware controls, and Server-Sent Event updates.
- Signed local demo sessions; REST and SSE reads are scoped to one tenant.
- Separate API and worker containers defined in `compose.yaml`.
- Automated unit tests and a GitHub Actions test workflow.

## Explicitly simulated or local-only

- Cloud execution never reaches AWS; it uses `SimulatedCloudAdapter`.
- Local demo identity is not a replacement for enterprise OIDC/SSO.
- SQLite and the in-process event broker are suitable for the local prototype only.
- Docker Desktop was unavailable while preparing this project, so the Compose configuration was syntax-checked but not run in this workspace.

## Production replacement plan

| Prototype component | Production component |
|---|---|
| Signed demo cookie | OIDC / SSO session |
| SQLite | PostgreSQL |
| SQLite job table | SQS or managed durable queue |
| In-process SSE broker | Redis Pub/Sub or managed event bus |
| Simulated adapter | Sandbox-first AWS adapter with tenant-scoped IAM role |
| Docker Compose | Container platform plus Terraform-provisioned infrastructure |

## Run

```bash
make run
make test
```

Then open `http://127.0.0.1:8000` and use the local demo sign-in panel.
