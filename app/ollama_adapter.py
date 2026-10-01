"""Local Ollama adapter that turns real response telemetry into AI usage events."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.ai_costs import AIUsageInput


class OllamaUnavailable(RuntimeError):
    """Raised when a configured Ollama endpoint is not reachable."""


@dataclass(frozen=True)
class OllamaRuntimeConfig:
    base_url: str = "http://127.0.0.1:11434"
    hourly_capacity_cost: float = 1.20
    effective_concurrency: int = 1


class OllamaAdapter:
    """Calls Ollama and captures the final response's actual usage telemetry.

    Runtime cost is an allocation of a provisioned server's hourly capacity. It is
    intentionally separate from a model provider's token price: local models have
    no API-token invoice, but the infrastructure has a real running cost.
    """

    def __init__(self, config: OllamaRuntimeConfig | None = None, post: Callable[[str, dict[str, object]], dict[str, object]] | None = None) -> None:
        self.config = config or OllamaRuntimeConfig()
        self._post = post or self._http_post

    def health(self) -> bool:
        try:
            self._http_get("/api/tags")
            return True
        except OllamaUnavailable:
            return False

    def generate_usage(
        self, tenant_id: str, app: str, customer: str, end_user: str, model: str, prompt: str,
        max_tokens: int = 120,
    ) -> tuple[str, AIUsageInput, dict[str, object]]:
        response = self._post("/api/generate", {
            "model": model, "prompt": prompt, "stream": False, "options": {"num_predict": max_tokens},
        })
        total_seconds = int(response.get("total_duration", 0)) / 1_000_000_000
        concurrency = max(self.config.effective_concurrency, 1)
        runtime_cost = round(total_seconds * (self.config.hourly_capacity_cost / 3_600) / concurrency, 8)
        usage = AIUsageInput(
            tenant_id=tenant_id, app=app, customer=customer, end_user=end_user,
            provider="ollama", model=str(response.get("model", model)),
            input_tokens=int(response.get("prompt_eval_count", 0)),
            output_tokens=int(response.get("eval_count", 0)),
            cached_input_tokens=int(response.get("prompt_eval_cached_count") or 0),
            compute_cost=runtime_cost, data_cost=0, request_id=f"ollama-{uuid.uuid4()}",
        )
        telemetry = {
            "total_duration_seconds": round(total_seconds, 6),
            "load_duration_seconds": round(int(response.get("load_duration", 0)) / 1_000_000_000, 6),
            "eval_duration_seconds": round(int(response.get("eval_duration", 0)) / 1_000_000_000, 6),
            "hourly_capacity_cost": self.config.hourly_capacity_cost,
            "effective_concurrency": concurrency,
            "response": str(response.get("response", "")),
        }
        return str(response.get("response", "")), usage, telemetry

    def _http_post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{self.config.base_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode(), headers={"content-type": "application/json"}, method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - endpoint is local/configured by deployment.
                return json.loads(response.read().decode())
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise OllamaUnavailable(f"Ollama is unavailable at {self.config.base_url}.") from error

    def _http_get(self, path: str) -> dict[str, object]:
        try:
            with urlopen(f"{self.config.base_url.rstrip('/')}{path}", timeout=5) as response:  # noqa: S310 - endpoint is local/configured by deployment.
                return json.loads(response.read().decode())
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise OllamaUnavailable(f"Ollama is unavailable at {self.config.base_url}.") from error
