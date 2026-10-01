import unittest

from app.domain import ActionStatus, AnomalyInput, RemediationService, Repository, WorkflowError


def qualified_anomaly(**changes: object) -> AnomalyInput:
    payload: dict[str, object] = {
        "tenant_id": "acme-health", "resource_id": "i-demo-001", "resource_type": "ec2",
        "environment": "nonprod", "owner": "data-platform", "auto_stop": True,
        "idle_hours": 96, "current_daily_cost": 380, "expected_daily_cost": 45,
    }
    payload.update(changes)
    return AnomalyInput(**payload)  # type: ignore[arg-type]


class RemediationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RemediationService(Repository())

    def test_happy_path_is_auditable_and_reversible(self) -> None:
        created = self.service.ingest_anomaly(qualified_anomaly())
        action_id = str(created["action_id"])
        self.assertTrue(created["eligible"])
        self.assertEqual(created["projected_monthly_savings"], 11400)

        self.assertEqual(self.service.approve(action_id, "alex")["status"], ActionStatus.APPROVED)
        executed = self.service.execute(action_id, "alex")
        self.assertEqual(executed["status"], ActionStatus.SUCCEEDED)
        self.assertIn("stopped", str(executed["cloud_result"]))
        rolled_back = self.service.rollback(action_id, "alex")
        self.assertEqual(rolled_back["status"], ActionStatus.ROLLED_BACK)

        events = self.service.repository.get_audit_events(action_id)
        self.assertEqual([event["event_type"] for event in events], [
            "ACTION_PROPOSED", "ACTION_APPROVED", "EXECUTION_STARTED", "EXECUTION_SUCCEEDED",
            "ROLLBACK_STARTED", "ROLLBACK_SUCCEEDED",
        ])

    def test_production_resource_is_not_eligible(self) -> None:
        result = self.service.ingest_anomaly(qualified_anomaly(environment="production"))
        self.assertFalse(result["eligible"])
        self.assertNotIn("action_id", result)

    def test_action_requires_approval_and_cannot_execute_twice(self) -> None:
        action_id = str(self.service.ingest_anomaly(qualified_anomaly())["action_id"])
        with self.assertRaisesRegex(WorkflowError, "Only approved"):
            self.service.execute(action_id, "alex")
        self.service.approve(action_id, "alex")
        self.service.execute(action_id, "alex")
        with self.assertRaisesRegex(WorkflowError, "Only approved"):
            self.service.execute(action_id, "alex")
