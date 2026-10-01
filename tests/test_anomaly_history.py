import unittest

from app.domain import AnomalyInput, RemediationService, Repository


class AnomalyHistoryTests(unittest.TestCase):
    def test_stores_policy_verdict_for_dashboard_history(self) -> None:
        repository = Repository()
        service = RemediationService(repository)
        service.ingest_anomaly(AnomalyInput(
            tenant_id="acme", resource_id="i-production", resource_type="ec2", environment="production",
            owner="platform", auto_stop=True, idle_hours=96, current_daily_cost=200, expected_daily_cost=30,
        ))
        anomaly = repository.list_anomalies("acme")[0]
        self.assertEqual(anomaly["verdict_eligible"], 0)
        self.assertIn("Production resources", str(anomaly["verdict_reason"]))
