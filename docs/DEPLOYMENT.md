# Deployment guide

## Local containers

Copy `.env.example` to `.env`, choose a development secret, then run:

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`. The `api` and `worker` services are separate containers sharing a local development volume. The API records approved actions in the durable queue; the worker claims and processes them.

```text
Browser → api container → shared local data volume ← worker container
```

## Production topology

Do not use the SQLite shared-volume arrangement for a multi-instance production deployment. Replace the local components before scaling:

```text
API containers      → load balancer → OIDC identity provider
Worker containers   → SQS / managed queue
Database            → PostgreSQL
SSE fan-out         → Redis Pub/Sub
Secrets             → cloud secret manager
Cloud actions       → per-tenant, least-privilege IAM roles
```

## Deployment order

1. Build and scan the container image.
2. Provision the network, container platform, PostgreSQL, queue, Redis, secret storage, and monitoring with Terraform.
3. Store the image in a container registry.
4. Deploy API and worker services separately.
5. Configure OIDC and disable `ALLOW_DEMO_AUTH`.
6. Replace the simulated adapter only with a dedicated sandbox account and narrowly scoped IAM role.

No cloud infrastructure is created by this repository automatically. Deploying to AWS requires an account, a reviewed Terraform configuration, and explicit authorization.
