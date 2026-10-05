import unittest

from app.ai_costs import AICostService, AIUsageInput
from app.domain import Repository


def usage(**changes: object) -> AIUsageInput:
    payload: dict[str, object] = {
        "tenant_id": "tenant-a", "app": "support-assistant", "customer": "acme",
        "end_user": "jane@acme.com", "provider": "openai", "model": "gpt-4o-mini",
        "input_tokens": 1_000_000, "output_tokens": 500_000, "cached_input_tokens": 200_000,
        "compute_cost": 1, "data_cost": 0.5, "request_id": "request-1",
    }
    payload.update(changes)
    return AIUsageInput(**payload)  # type: ignore[arg-type]


class AICostServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AICostService(Repository())

    def test_estimate_includes_tokens_compute_and_data(self) -> None:
        estimate = self.service.estimate(usage())
        self.assertEqual(estimate["inference_cost"], 0.435)
        self.assertEqual(estimate["total_cost"], 1.935)

    def test_preflight_blocks_when_projected_spend_exceeds_app_budget(self) -> None:
        self.service.set_budget("tenant-a", "support-assistant", monthly_limit=2)
        self.service.record_usage(usage())
        result = self.service.preflight(usage(request_id="request-2"))
        self.assertEqual(result["decision"], "BLOCK")
        self.assertFalse(result["permitted"])

    def test_preflight_warns_when_projected_spend_crosses_warning_threshold(self) -> None:
        self.service.set_budget("tenant-a", "support-assistant", monthly_limit=5, warning_percent=70)
        self.service.record_usage(usage())
        result = self.service.preflight(usage(request_id="request-2"))
        self.assertEqual(result["decision"], "WARN")
        self.assertTrue(result["permitted"])

    def test_overview_attributes_cost_to_model_customer_and_app(self) -> None:
        self.service.record_usage(usage())
        overview = self.service.overview("tenant-a")
        self.assertEqual(overview["request_count"], 1)
        self.assertEqual(overview["by_app"][0]["name"], "support-assistant")
        self.assertEqual(overview["by_customer"][0]["name"], "acme")

    def test_blocked_frontier_model_can_route_to_an_approved_fallback(self) -> None:
        self.service.set_budget("tenant-a", "support-assistant", monthly_limit=4)
        self.service.record_usage(usage())
        requested = usage(request_id="request-2", model="gpt-4o")
        blocked = self.service.preflight(requested)
        self.assertEqual(blocked["decision"], "BLOCK")
        self.assertEqual(blocked["recommended_fallback"]["model"], "gpt-4o-mini")
        self.assertTrue(blocked["recommended_fallback"]["permitted"])

        routed = self.service.preflight(requested, allow_fallback=True)
        self.assertTrue(routed["routed_to_fallback"])
        self.assertEqual(routed["effective_model"], "gpt-4o-mini")
        self.assertTrue(routed["permitted"])
