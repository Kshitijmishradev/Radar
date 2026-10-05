# Radar demo script

This is a 4–5 minute recruiter demo. It is designed to show product judgment and
backend engineering, rather than every screen in the application.

## Before recording

In the project directory, reset the recording tenant:

```bash
make demo
```

Start the API without its embedded worker so the approval queue remains visible:

```bash
make demo-api
```

Open `http://127.0.0.1:8000`. Keep a second terminal ready with this command,
but do not run it yet:

```bash
make worker
```

## 1. Opening — the problem (20 seconds)

Say: “Radar is a FinOps control plane for both cloud and AI spending. It makes
cost decisions explainable, approval-gated, and auditable.”

Sign in to the **Video Demo** tenant as **Alex Morgan — Operator**.

Point out the named user, tenant, and role in the header. Open the approval-ready
cloud action. The action is visible, but its approval controls are locked. Explain
that hiding the button is not the security boundary—the API enforces the same role
check.

## 2. Cloud policy and human approval (75 seconds)

1. Show the anomaly table. Point out the one eligible non-production EC2 instance
   and the seven rejected examples.
2. Pick the production instance row and read its policy explanation: production is
   never eligible for automatic remediation.
3. Switch role to **Priya Sharma — Approver**.
4. Reopen the eligible action, show the policy evidence and projected savings, then
   select **Approve**.
5. Point out the audit entry and the queued action status.
6. In the second terminal, run `make worker` once. The SSE-connected dashboard
   updates when the simulated action succeeds.
7. Switch back to **Alex Morgan — Operator** and use **Rollback / start instance**.

Say: “The design separates policy evaluation, human approval, durable work, and
execution. That prevents an anomaly detector from making a high-impact change by
itself.”

## 3. AI budget policy (75 seconds)

Open **AI control** and sign in as **Alex Morgan — Operator**.

In the budget gate simulator, run each request shape in order:

1. **Safe request** — show `ALLOW` and the projected spend.
2. **Near budget** — show `WARN`; the request may proceed, but the dashboard
   explains it has crossed the warning threshold.
3. **Over budget** — show `BLOCK`, then choose the explicit GPT-4o mini fallback.

Say: “Radar checks cost before an LLM request is sent. It never silently downgrades
a model; the caller explicitly accepts the approved fallback.”

## 4. Self-hosted AI cost (40 seconds, optional)

If Ollama and `llama3.2:3b` are available locally, select **Run Ollama request**.
Show the real token count, measured duration, and allocated runtime cost.

Then select **Run 3-step RTX 4090 replay**. Explain that the model work is real,
but the RTX 4090 amount is a lease-rate replay using local runtime—not a claim
that the local machine has RTX 4090 performance.

## 5. Close — production thinking (25 seconds)

Say: “This is deliberately safe locally: cloud changes are simulated. For
production, I would replace SQLite with PostgreSQL, the local event broker with
Redis or a managed event bus, the local queue with a managed queue, demo sessions
with OIDC, and the simulated adapter with tenant-scoped IAM roles.”

End on the README production roadmap or `docs/DEPLOYMENT.md`.
