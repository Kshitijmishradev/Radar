import unittest

from app.ai_costs import AICostService, AIUsageInput
from app.domain import Repository
from app.ollama_scenarios import IterativeOllamaScenario, RUNPOD_RTX_4090_SECURE


class FakeAdapter:
    def __init__(self, _: object) -> None:
        self.count = 0

    def generate_usage(self, tenant_id: str, app: str, customer: str, end_user: str, model: str, prompt: str, max_tokens: int) -> tuple[str, AIUsageInput, dict[str, object]]:
        self.count += 1
        return (
            f"draft {self.count}",
            AIUsageInput(tenant_id, app, customer, end_user, "ollama", model, 20, 10, compute_cost=0.002, request_id=f"fake-{self.count}"),
            {"total_duration_seconds": 2, "response": f"draft {self.count}"},
        )


class OllamaScenarioTests(unittest.TestCase):
    def test_iterative_scenario_records_three_measured_steps_at_named_market_rate(self) -> None:
        service = AICostService(Repository())
        result = IterativeOllamaScenario(service, "http://localhost", FakeAdapter).run("tenant-a", "llama3.2:3b")
        self.assertEqual(result["profile"]["id"], "runpod-rtx-4090-secure")
        self.assertEqual(result["profile"]["hourly_capacity_cost"], 0.74)
        self.assertEqual(len(result["steps"]), 3)
        self.assertEqual(result["total_tokens"], 90)
        self.assertEqual(result["total_cost"], 0.006)
        self.assertEqual(service.overview("tenant-a")["request_count"], 3)
