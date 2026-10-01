"""Durable job queue and local worker for remediation execution."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import RemediationService, Repository


MAX_EXECUTION_ATTEMPTS = 3


@dataclass(frozen=True)
class JobOutcome:
    job: dict[str, object]
    action: dict[str, object] | None
    error: str | None = None


class DurableJobQueue:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def enqueue_execution(self, action: dict[str, object]) -> dict[str, object]:
        return self.repository.create_execution_job(action)


class RemediationWorker:
    """Processes one durable job at a time; can run in-process or as a standalone process."""

    def __init__(self, repository: Repository, remediation_service: RemediationService) -> None:
        self.repository = repository
        self.remediation_service = remediation_service

    def process_next(self) -> JobOutcome | None:
        job = self.repository.claim_next_job()
        if not job:
            return None
        try:
            if job["job_type"] != "EXECUTE_ACTION":
                raise ValueError(f"Unsupported job type: {job['job_type']}")
            action = self.remediation_service.execute(str(job["action_id"]), actor="remediation-worker")
            self.repository.complete_job(str(job["id"]))
            return JobOutcome(self.repository.get_job(str(job["id"])) or job, action)
        except Exception as error:
            attempts = int(job["attempts"])
            self.repository.fail_job(str(job["id"]), str(error), retry=attempts < MAX_EXECUTION_ATTEMPTS)
            return JobOutcome(self.repository.get_job(str(job["id"])) or job, None, str(error))
