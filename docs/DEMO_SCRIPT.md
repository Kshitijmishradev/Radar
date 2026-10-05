# Radar demo script — the production cost-control story

This is a 4-minute recruiter demo. It leads with the operational problem Radar
solves, then uses the cloud workflow to prove the backend safety model.

## Before recording

In the project directory, prepare the deterministic demo data:

```bash
make demo
```

Start the API without its embedded worker so the approved cloud action remains
queued until you deliberately run it:

```bash
make demo-api
```

Open the local address printed by the server (normally `http://127.0.0.1:8000`).
Keep a second terminal ready with this command, but do not run it yet:

```bash
make worker
```

Start at the **Video Demo** tenant. Sign in as **Alex Morgan — Operator** for
the AI section.

## 0:00–0:35 — Start with the business problem

Say:

> “Radar is not another cloud-cost dashboard. It is a decision-control layer
> that prevents cloud and AI spend from growing silently. Here is a realistic
> example: Support Assistant has already consumed $31,290 of its $35,000 monthly
> AI guardrail. A scheduled high-volume GPT-4o workload would cost another
> $4,887.50 and push the projected month-end spend to $36,177.50. Without Radar,
> that workload runs and the overrun is discovered later. With Radar, policy is
> evaluated before the workload is dispatched.”

## 0:35–1:35 — Prove the AI decision happens before spend

Open **AI control**. Point out:

- **$39,970 month-to-date AI cost** across the recording-demo workload ledger.
- **Support Assistant: $31,290 of $35,000 (89.4%)** in the app-budget panel.
- The decision history showing `ALLOW`, `WARN`, `BLOCK`, and prior accepted
  fallbacks.

Then select **High-volume batch** and choose **Evaluate selected workload**.

Say:

> “This is a high-volume production batch, not a single chat message. Radar
> estimates the provider tokens, self-hosted compute, and data cost before the
> model call. The policy blocks it because it would exceed the application’s
> $35,000 budget.”

Point out the result: **$4,887.50 estimated cost** and **$36,177.50 projected
spend**.

Choose **Use openai / gpt-4o-mini**.

Say:

> “Radar does not silently downgrade a customer-facing model. It offers an
> approved alternative and the caller explicitly accepts it. The fallback costs
> $1,750.25, keeps projected spend at $33,040.25, and saves an estimated
> $3,137.25 for this workload.”

## 1:35–2:25 — Show the cloud use case

Open **Cloud control**. Stay signed in as **Alex Morgan — Operator**.

Say:

> “The same design applies to cloud spend. Radar found an idle non-production
> instance that costs $220 per day, or $6,600 per month. The goal is not to let
> an anomaly detector turn off infrastructure by itself. The goal is to make a
> safe, explainable decision.”

Point out:

- **1 eligible signal and 7 policy denials**.
- The **production** row and its denial explanation.
- The decision inbox showing **$6,600** in monthly savings awaiting approval.

Say:

> “Production resources are rejected by policy. Other signals are rejected when
> they are too cheap, recently active, opted out, unowned, staging, or unsupported.
> The reason is preserved with every decision.”

## 2:25–3:15 — Prove RBAC and durable execution

Say:

> “Alex can investigate the decision, but cannot approve it. The lock in the
> interface is helpful, but the backend role check is the real security boundary.”

Switch role to **Priya Sharma — Approver**. Select **Review decision** and
point to the policy evidence. Then choose **Approve**.

Say:

> “Approval changes business state; it does not call the cloud provider directly
> from a browser request. Radar writes a durable job and a worker executes it
> separately. That means the workflow can safely retry if an API server restarts
> or the cloud provider is slow.”

In the second terminal, run:

```bash
make worker
```

Return to the dashboard and point to **Execution started**, **Execution
succeeded**, and the audit trail.

Say:

> “The update arrives through Server-Sent Events. The browser sees the state
> change without polling, while the audit trail records who proposed, approved,
> and executed the action.”

## 3:15–4:00 — Close with engineering judgment

Say:

> “Radar’s core value is that it makes spend control operational. For AI, it can
> stop or reroute an expensive workload before money is spent. For cloud, it
> separates detection, policy, human authorization, durable background work, and
> execution. That protects reliability while still giving FinOps teams control.”

> “This local demo is deliberately safe: cloud changes are simulated. In
> production, I would use OIDC for company sign-in, PostgreSQL for the audit and
> cost ledger, Redis or a managed event bus for multi-instance live updates, a
> managed queue and workers, tenant-scoped IAM roles for cloud actions, and
> Terraform to provision the infrastructure reproducibly.”

End on the dashboard rather than a terminal.
