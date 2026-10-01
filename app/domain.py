"""Core deterministic remediation workflow with a SQLite persistence layer."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Iterator


class ActionStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class AnomalyInput:
    tenant_id: str
    resource_id: str
    resource_type: str
    environment: str
    owner: str | None
    auto_stop: bool
    idle_hours: float
    current_daily_cost: float
    expected_daily_cost: float


@dataclass(frozen=True)
class PolicyDecision:
    eligible: bool
    reason: str
    projected_monthly_savings: float


class WorkflowError(ValueError):
    """Raised when a workflow command would create an invalid state transition."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class PolicyEngine:
    """Intentionally explicit rules for the MVP's single remediation policy."""

    MIN_IDLE_HOURS = 72
    MIN_DAILY_COST = 100

    def evaluate(self, anomaly: AnomalyInput) -> PolicyDecision:
        if anomaly.resource_type.lower() != "ec2":
            return PolicyDecision(False, "Only EC2 resources are supported in this MVP.", 0)
        if anomaly.environment.lower() == "production":
            return PolicyDecision(False, "Production resources cannot be remediated automatically.", 0)
        if anomaly.environment.lower() != "nonprod":
            return PolicyDecision(False, "Only non-production resources match the stop policy.", 0)
        if not anomaly.owner:
            return PolicyDecision(False, "Resource owner is required before a remediation can be proposed.", 0)
        if not anomaly.auto_stop:
            return PolicyDecision(False, "Resource is not opted into automatic stopping.", 0)
        if anomaly.idle_hours < self.MIN_IDLE_HOURS:
            return PolicyDecision(False, f"Resource has been idle for less than {self.MIN_IDLE_HOURS} hours.", 0)
        if anomaly.current_daily_cost < self.MIN_DAILY_COST:
            return PolicyDecision(False, f"Daily cost is below ${self.MIN_DAILY_COST} action threshold.", 0)

        return PolicyDecision(
            True,
            "Matches stop-idle-nonprod-ec2 policy; explicit approval is required.",
            round(anomaly.current_daily_cost * 30, 2),
        )


class SimulatedCloudAdapter:
    """A deterministic, side-effect-free replacement for an AWS SDK adapter."""

    def stop_instance(self, resource_id: str) -> dict[str, str]:
        return {"resource_id": resource_id, "cloud_state": "stopped", "adapter": "simulated"}

    def start_instance(self, resource_id: str) -> dict[str, str]:
        return {"resource_id": resource_id, "cloud_state": "running", "adapter": "simulated"}


class Repository:
    def __init__(self, database_url: str = ":memory:") -> None:
        self.database_url = database_url
        if database_url != ":memory:":
            Path(database_url).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_url, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _create_schema(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS anomalies (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    owner TEXT,
                    auto_stop INTEGER NOT NULL,
                    idle_hours REAL NOT NULL,
                    current_daily_cost REAL NOT NULL,
                    expected_daily_cost REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS remediation_actions (
                    id TEXT PRIMARY KEY,
                    anomaly_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    projected_monthly_savings REAL NOT NULL,
                    policy_reason TEXT NOT NULL,
                    cloud_result TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(anomaly_id) REFERENCES anomalies(id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(action_id) REFERENCES remediation_actions(id)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(job_type, action_id),
                    FOREIGN KEY(action_id) REFERENCES remediation_actions(id)
                );
                """
            )

    def save_anomaly(self, anomaly_id: str, anomaly: AnomalyInput) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO anomalies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (anomaly_id, anomaly.tenant_id, anomaly.resource_id, anomaly.resource_type,
                 anomaly.environment, anomaly.owner, anomaly.auto_stop, anomaly.idle_hours,
                 anomaly.current_daily_cost, anomaly.expected_daily_cost, utc_now()),
            )

    def save_action(self, action: dict[str, object]) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO remediation_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (action["id"], action["anomaly_id"], action["tenant_id"], action["resource_id"],
                 action["action_type"], action["status"], action["projected_monthly_savings"],
                 action["policy_reason"], None, action["created_at"], action["updated_at"]),
            )

    def get_action(self, action_id: str, tenant_id: str | None = None) -> dict[str, object] | None:
        query = "SELECT * FROM remediation_actions WHERE id = ?"
        parameters: tuple[str, ...] = (action_id,)
        if tenant_id:
            query += " AND tenant_id = ?"
            parameters = (action_id, tenant_id)
        row = self._connection.execute(query, parameters).fetchone()
        return dict(row) if row else None

    def list_actions(self, tenant_id: str | None = None) -> list[dict[str, object]]:
        if tenant_id:
            rows = self._connection.execute(
                "SELECT * FROM remediation_actions WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)
            ).fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM remediation_actions ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def update_action(self, action_id: str, status: ActionStatus, cloud_result: dict[str, str] | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE remediation_actions SET status = ?, cloud_result = COALESCE(?, cloud_result), updated_at = ? WHERE id = ?",
                (status.value, json.dumps(cloud_result) if cloud_result else None, utc_now(), action_id),
            )

    def add_audit_event(self, action_id: str, event_type: str, detail: dict[str, object], actor: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), action_id, event_type, json.dumps(detail), actor, utc_now()),
            )

    def get_audit_events(self, action_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT * FROM audit_events WHERE action_id = ? ORDER BY created_at ASC", (action_id,)
        ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["detail"] = json.loads(str(event["detail"]))
            events.append(event)
        return events

    def create_execution_job(self, action: dict[str, object]) -> dict[str, object]:
        """Create one durable execution job per action; repeat requests return that job."""
        existing = self._connection.execute(
            "SELECT * FROM jobs WHERE job_type = 'EXECUTE_ACTION' AND action_id = ?", (action["id"],)
        ).fetchone()
        if existing:
            return dict(existing)
        job_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO jobs (id, job_type, tenant_id, action_id, status, attempts, created_at, updated_at)
                   VALUES (?, 'EXECUTE_ACTION', ?, ?, 'PENDING', 0, ?, ?)""",
                (job_id, action["tenant_id"], action["id"], now, now),
            )
        return self.get_job(job_id) or {}

    def get_job(self, job_id: str) -> dict[str, object] | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, tenant_id: str | None = None) -> list[dict[str, object]]:
        if tenant_id:
            rows = self._connection.execute(
                "SELECT * FROM jobs WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)
            ).fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def claim_next_job(self) -> dict[str, object] | None:
        """Atomically claim one pending job so two workers cannot run it together."""
        conn = self._connection
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                conn.commit()
                return None
            job = dict(row)
            now = utc_now()
            conn.execute(
                """UPDATE jobs SET status = 'PROCESSING', attempts = attempts + 1,
                   started_at = ?, updated_at = ? WHERE id = ?""",
                (now, now, job["id"]),
            )
            conn.commit()
            return self.get_job(str(job["id"]))
        except Exception:
            conn.rollback()
            raise

    def complete_job(self, job_id: str) -> None:
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'SUCCEEDED', completed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, job_id),
            )

    def fail_job(self, job_id: str, error_message: str, retry: bool) -> None:
        now = utc_now()
        next_status = "PENDING" if retry else "FAILED"
        with self.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, error_message = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                (next_status, error_message, now, now if not retry else None, job_id),
            )


class RemediationService:
    def __init__(self, repository: Repository, policy_engine: PolicyEngine | None = None,
                 cloud_adapter: SimulatedCloudAdapter | None = None) -> None:
        self.repository = repository
        self.policy_engine = policy_engine or PolicyEngine()
        self.cloud_adapter = cloud_adapter or SimulatedCloudAdapter()

    def ingest_anomaly(self, anomaly: AnomalyInput) -> dict[str, object]:
        anomaly_id = str(uuid.uuid4())
        self.repository.save_anomaly(anomaly_id, anomaly)
        decision = self.policy_engine.evaluate(anomaly)
        result: dict[str, object] = {"anomaly_id": anomaly_id, "eligible": decision.eligible, "reason": decision.reason}
        if not decision.eligible:
            return result

        now = utc_now()
        action = {
            "id": str(uuid.uuid4()), "anomaly_id": anomaly_id, "tenant_id": anomaly.tenant_id,
            "resource_id": anomaly.resource_id, "action_type": "STOP_EC2_INSTANCE",
            "status": ActionStatus.PENDING_APPROVAL.value,
            "projected_monthly_savings": decision.projected_monthly_savings,
            "policy_reason": decision.reason, "created_at": now, "updated_at": now,
        }
        self.repository.save_action(action)
        self.repository.add_audit_event(action["id"], "ACTION_PROPOSED", {
            "anomaly_id": anomaly_id, "policy_reason": decision.reason,
            "projected_monthly_savings": decision.projected_monthly_savings,
        }, "system")
        result["action_id"] = action["id"]
        result["projected_monthly_savings"] = decision.projected_monthly_savings
        return result

    def _require_action(self, action_id: str) -> dict[str, object]:
        action = self.repository.get_action(action_id)
        if not action:
            raise WorkflowError("Action not found.")
        return action

    def get_action_or_raise(self, action_id: str) -> dict[str, object]:
        """Public read helper for API/workflow orchestration code."""
        return self._require_action(action_id)

    def approve(self, action_id: str, actor: str) -> dict[str, object]:
        action = self._require_action(action_id)
        if action["status"] != ActionStatus.PENDING_APPROVAL.value:
            raise WorkflowError("Only pending actions can be approved.")
        self.repository.update_action(action_id, ActionStatus.APPROVED)
        self.repository.add_audit_event(action_id, "ACTION_APPROVED", {}, actor)
        return self._require_action(action_id)

    def reject(self, action_id: str, actor: str) -> dict[str, object]:
        action = self._require_action(action_id)
        if action["status"] != ActionStatus.PENDING_APPROVAL.value:
            raise WorkflowError("Only pending actions can be rejected.")
        self.repository.update_action(action_id, ActionStatus.REJECTED)
        self.repository.add_audit_event(action_id, "ACTION_REJECTED", {}, actor)
        return self._require_action(action_id)

    def execute(self, action_id: str, actor: str) -> dict[str, object]:
        action = self._require_action(action_id)
        if action["status"] != ActionStatus.APPROVED.value:
            raise WorkflowError("Only approved actions can be executed once.")
        self.repository.update_action(action_id, ActionStatus.EXECUTING)
        self.repository.add_audit_event(action_id, "EXECUTION_STARTED", {}, actor)
        result = self.cloud_adapter.stop_instance(str(action["resource_id"]))
        self.repository.update_action(action_id, ActionStatus.SUCCEEDED, result)
        self.repository.add_audit_event(action_id, "EXECUTION_SUCCEEDED", result, actor)
        return self._require_action(action_id)

    def rollback(self, action_id: str, actor: str) -> dict[str, object]:
        action = self._require_action(action_id)
        if action["status"] != ActionStatus.SUCCEEDED.value:
            raise WorkflowError("Only successfully executed actions can be rolled back.")
        self.repository.update_action(action_id, ActionStatus.ROLLING_BACK)
        self.repository.add_audit_event(action_id, "ROLLBACK_STARTED", {}, actor)
        result = self.cloud_adapter.start_instance(str(action["resource_id"]))
        self.repository.update_action(action_id, ActionStatus.ROLLED_BACK, result)
        self.repository.add_audit_event(action_id, "ROLLBACK_SUCCEEDED", result, actor)
        return self._require_action(action_id)
