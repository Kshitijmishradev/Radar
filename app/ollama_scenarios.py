"""Repeatable, iterative Ollama workloads for capacity-cost validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.ai_costs import AICostService
from app.ollama_adapter import OllamaAdapter, OllamaRuntimeConfig


@dataclass(frozen=True)
class GPURentalProfile:
    id: str
    label: str
    provider: str
    hourly_capacity_cost: float
    note: str


# Source checked 2026-10-01. This is intentionally a named scenario setting,
# not a live price feed; production should update it from a reviewed price source.
RUNPOD_RTX_4090_SECURE = GPURentalProfile(
    id="runpod-rtx-4090-secure",
    label="Runpod RTX 4090 Secure Cloud",
    provider="Runpod",
    hourly_capacity_cost=0.74,
    note="24 GB RTX 4090 dedicated pod; $0.74/hour lease-rate replay.",
)


class IterativeOllamaScenario:
    """Runs a small agent-style chain and records every measured inference step."""

    def __init__(self, service: AICostService, base_url: str, adapter_factory: Callable[[OllamaRuntimeConfig], OllamaAdapter] = OllamaAdapter) -> None:
        self.service = service
        self.base_url = base_url
        self.adapter_factory = adapter_factory

    def run(self, tenant_id: str, model: str, profile: GPURentalProfile = RUNPOD_RTX_4090_SECURE) -> dict[str, object]:
        adapter = self.adapter_factory(OllamaRuntimeConfig(
            base_url=self.base_url, hourly_capacity_cost=profile.hourly_capacity_cost,
        ))
        brief = (
            "A SaaS support assistant handles 120,000 chats per day. It uses an LLM for triage, "
            "classification and response drafting. The team needs lower AI cost without sending "
            "sensitive customer text to a third party."
        )
        prompts = [
            f"You are a FinOps analyst. Read this brief: {brief}\nStep 1: list exactly three measurable cost risks in concise bullets.",
        ]
        steps: list[dict[str, object]] = []
        previous = ""
        for index in range(3):
            if index == 1:
                prompts.append(
                    f"Brief: {brief}\nStep 1 draft:\n{previous}\nStep 2: turn the risks into a three-step cost-control plan. Keep each step measurable."
                )
            elif index == 2:
                prompts.append(
                    f"Brief: {brief}\nWorking plan:\n{previous}\nStep 3: critique the plan, then provide a final three-bullet recommendation with a cost metric for each bullet."
                )
            text, usage, telemetry = adapter.generate_usage(
                tenant_id=tenant_id, app="gpu-rental-evaluation", customer="scenario-lab",
                end_user="load-test@radar.local", model=model, prompt=prompts[index], max_tokens=110,
            )
            event = self.service.record_usage(usage)
            previous = text
            steps.append({
                "step": index + 1, "response": text, "usage": event, "telemetry": telemetry,
            })
        total_cost = round(sum(float(step["usage"]["total_cost"]) for step in steps), 8)
        total_duration = round(sum(float(step["telemetry"]["total_duration_seconds"]) for step in steps), 6)
        total_tokens = sum(int(step["usage"]["input_tokens"]) + int(step["usage"]["output_tokens"]) for step in steps)
        return {
            "profile": profile.__dict__, "steps": steps, "total_cost": total_cost,
            "total_duration_seconds": total_duration, "total_tokens": total_tokens,
            "method": "Lease-rate replay: local measured runtime multiplied by the named GPU hourly capacity rate.",
        }
