"""Load repeatable application-AI costs for the Radar AI dashboard.

Run with: .venv/bin/python -m scripts.seed_ai_demo
"""

from __future__ import annotations

import os
from pathlib import Path

from app.ai_costs import AICostService, AIUsageInput
from app.domain import Repository


TENANT = "demo-video"
# The recording demo represents high-volume production workloads (for example,
# scheduled document processing), rather than one person sending one chat prompt.
# This keeps the financial scenario credible for an organization that needs FinOps
# controls: $35K per application per month, not a hobby-project budget.
WORKLOAD_SCALE = 1_000
SCALED_FIELDS = (
    "input_tokens", "output_tokens", "cached_input_tokens", "compute_cost", "data_cost",
)


def usage(request_id: str, **changes: object) -> AIUsageInput:
    payload: dict[str, object] = {
        "tenant_id": TENANT, "app": "support-assistant", "customer": "acme-corp",
        "end_user": "jane@acme.com", "provider": "openai", "model": "gpt-4o",
        "input_tokens": 2_800_000, "output_tokens": 700_000, "cached_input_tokens": 600_000,
        "compute_cost": 0.72, "data_cost": 0.24, "request_id": request_id,
    }
    payload.update(changes)
    for field in SCALED_FIELDS:
        payload[field] = payload[field] * WORKLOAD_SCALE  # type: ignore[operator]
    return AIUsageInput(**payload)  # type: ignore[arg-type]


def main() -> None:
    database_path = os.getenv("DATABASE_PATH", str(Path("data") / "radar.db"))
    service = AICostService(Repository(database_path))
    service.delete_tenant_data(TENANT)
    service.set_budget(TENANT, "support-assistant", monthly_limit=35_000, warning_percent=80)
    service.set_budget(TENANT, "claims-copilot", monthly_limit=35_000, warning_percent=80)
    events = [
        usage("ai-demo-001"),
        usage("ai-demo-002", customer="northstar-health", end_user="priya@northstar.com", input_tokens=2_200_000, output_tokens=540_000),
        usage("ai-demo-003", provider="anthropic", model="claude-haiku", customer="acme-corp", end_user="sam@acme.com", input_tokens=4_000_000, output_tokens=800_000, cached_input_tokens=1_000_000, compute_cost=0.19, data_cost=0.10),
        usage("ai-demo-004", app="claims-copilot", provider="anthropic", model="claude-sonnet", customer="northstar-health", end_user="kai@northstar.com", input_tokens=1_200_000, output_tokens=260_000, cached_input_tokens=100_000, compute_cost=0.45, data_cost=0.32),
        usage("ai-demo-005", app="claims-copilot", provider="openai", model="gpt-4o-mini", customer="northstar-health", end_user="kai@northstar.com", input_tokens=2_000_000, output_tokens=400_000, cached_input_tokens=800_000, compute_cost=0.12, data_cost=0.08),
    ]
    for event in events:
        service.record_usage(event)
    policy_cases = [
        (usage("ai-policy-001", app="claims-copilot", provider="openai", model="gpt-4o-mini", input_tokens=120_000, output_tokens=18_000, cached_input_tokens=20_000, compute_cost=0.03, data_cost=0.01), False),
        (usage("ai-policy-002", provider="openai", model="gpt-4o-mini", input_tokens=400_000, output_tokens=50_000, cached_input_tokens=80_000, compute_cost=0.10, data_cost=0.03), False),
        (usage("ai-policy-003", provider="openai", model="gpt-4o", input_tokens=900_000, output_tokens=140_000, cached_input_tokens=250_000, compute_cost=1.20, data_cost=0.35), False),
        (usage("ai-policy-004", provider="openai", model="gpt-4o", input_tokens=900_000, output_tokens=140_000, cached_input_tokens=250_000, compute_cost=1.20, data_cost=0.35), True),
    ]
    for policy_usage, allow_fallback in policy_cases:
        result = service.preflight(policy_usage, allow_fallback=allow_fallback)
        service.record_policy_decision(policy_usage, result)
    overview = service.overview(TENANT)
    print(f"Loaded {overview['request_count']} application-AI usage events for tenant '{TENANT}'.")
    print(f"Attributed cost-to-serve: ${overview['total_cost']:,.2f} across tokens, compute, and data.")
    print(f"Loaded {overview['policy_summary']['total_decisions']} AI policy decisions for the dashboard.")


if __name__ == "__main__":
    main()
