import unittest

from app.domain import AnomalyInput, PolicyEngine


def baseline(**changes: object) -> AnomalyInput:
    payload: dict[str, object] = {
        "tenant_id": "policy-test", "resource_id": "i-policy-001", "resource_type": "ec2",
        "environment": "nonprod", "owner": "platform", "auto_stop": True,
        "idle_hours": 96, "current_daily_cost": 200, "expected_daily_cost": 30,
    }
    payload.update(changes)
    return AnomalyInput(**payload)  # type: ignore[arg-type]


class PolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PolicyEngine()

    def test_all_policy_outcomes(self) -> None:
        cases = [
            ("eligible workload", {}, True, "Matches stop-idle-nonprod-ec2 policy", 6000),
            ("unsupported resource", {"resource_type": "rds"}, False, "Only EC2 resources", 0),
            ("production resource", {"environment": "production"}, False, "Production resources", 0),
            ("unsupported environment", {"environment": "staging"}, False, "Only non-production", 0),
            ("missing owner", {"owner": None}, False, "Resource owner is required", 0),
            ("not opted in", {"auto_stop": False}, False, "not opted into", 0),
            ("not idle long enough", {"idle_hours": 71}, False, "less than 72 hours", 0),
            ("cost below threshold", {"current_daily_cost": 99}, False, "below $100", 0),
        ]
        for name, changes, eligible, reason, savings in cases:
            with self.subTest(name=name):
                decision = self.engine.evaluate(baseline(**changes))
                self.assertEqual(decision.eligible, eligible)
                self.assertIn(reason, decision.reason)
                self.assertEqual(decision.projected_monthly_savings, savings)
