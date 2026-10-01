import unittest

from app.ai_costs import AICostService
from app.domain import Repository
from app.ollama_adapter import OllamaAdapter, OllamaRuntimeConfig


class OllamaAdapterTests(unittest.TestCase):
    def test_real_telemetry_becomes_self_hosted_capacity_cost(self) -> None:
        def fake_post(_: str, __: dict[str, object]) -> dict[str, object]:
            return {
                "model": "llama3.2:3b", "response": "Costs remain visible.",
                "prompt_eval_count": 40, "prompt_eval_cached_count": 10, "eval_count": 12,
                "total_duration": 10_000_000_000, "load_duration": 1_000_000_000,
                "eval_duration": 8_000_000_000,
            }

        adapter = OllamaAdapter(OllamaRuntimeConfig(hourly_capacity_cost=3.6), post=fake_post)
        text, usage, telemetry = adapter.generate_usage(
            "tenant-a", "support-assistant", "acme", "jane@acme.com", "llama3.2:3b", "hello"
        )
        self.assertEqual(text, "Costs remain visible.")
        self.assertEqual(usage.input_tokens, 40)
        self.assertEqual(usage.cached_input_tokens, 10)
        self.assertEqual(usage.output_tokens, 12)
        self.assertEqual(usage.compute_cost, 0.01)
        self.assertEqual(telemetry["total_duration_seconds"], 10)

        service = AICostService(Repository())
        event = service.record_usage(usage)
        self.assertEqual(event["total_cost"], 0.01)
