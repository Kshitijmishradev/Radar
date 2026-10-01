import unittest

from app.domain import ActionStatus, AnomalyInput, RemediationService, Repository
from app.jobs import DurableJobQueue, RemediationWorker


def qualifying_anomaly() -> AnomalyInput:
    return AnomalyInput(
        tenant_id="acme", resource_id="i-worker-001", resource_type="ec2", environment="nonprod",
        owner="platform", auto_stop=True, idle_hours=96, current_daily_cost=200, expected_daily_cost=30,
    )


class DurableJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Repository()
        self.service = RemediationService(self.repository)
        self.queue = DurableJobQueue(self.repository)
        self.worker = RemediationWorker(self.repository, self.service)

    def test_worker_claims_and_executes_an_approved_action(self) -> None:
        action_id = str(self.service.ingest_anomaly(qualifying_anomaly())["action_id"])
        action = self.service.approve(action_id, "approver")
        job = self.queue.enqueue_execution(action)

        outcome = self.worker.process_next()
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual(outcome.job["id"], job["id"])
        self.assertEqual(outcome.job["status"], "SUCCEEDED")
        self.assertEqual(outcome.action["status"], ActionStatus.SUCCEEDED)

    def test_approval_execution_job_is_idempotent(self) -> None:
        action_id = str(self.service.ingest_anomaly(qualifying_anomaly())["action_id"])
        action = self.service.approve(action_id, "approver")
        first = self.queue.enqueue_execution(action)
        second = self.queue.enqueue_execution(action)
        self.assertEqual(first["id"], second["id"])
