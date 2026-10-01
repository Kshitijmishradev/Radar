"""Load a repeatable tenant-scoped dataset for a dashboard recording.

Run with: .venv/bin/python scripts/seed_video_demo.py
"""

from __future__ import annotations

import os
from pathlib import Path

from app.domain import AnomalyInput, RemediationService, Repository


TENANT = "demo-video"


def anomaly(resource_id: str, **changes: object) -> AnomalyInput:
    payload: dict[str, object] = {
        "tenant_id": TENANT, "resource_id": resource_id, "resource_type": "ec2",
        "environment": "nonprod", "owner": "platform-team", "auto_stop": True,
        "idle_hours": 96, "current_daily_cost": 220, "expected_daily_cost": 30,
    }
    payload.update(changes)
    return AnomalyInput(**payload)  # type: ignore[arg-type]


def main() -> None:
    database_path = os.getenv("DATABASE_PATH", str(Path("data") / "radar.db"))
    repository = Repository(database_path)
    repository.delete_tenant_data(TENANT)
    service = RemediationService(repository)
    cases = [
        anomaly("i-video-savings"),
        anomaly("db-video-unsupported", resource_type="rds"),
        anomaly("i-video-production", environment="production"),
        anomaly("i-video-staging", environment="staging"),
        anomaly("i-video-unowned", owner=None),
        anomaly("i-video-optout", auto_stop=False),
        anomaly("i-video-active", idle_hours=24),
        anomaly("i-video-lowcost", current_daily_cost=60),
    ]
    result = [service.ingest_anomaly(item) for item in cases]
    print(f"Loaded {len(result)} video-demo anomalies for tenant '{TENANT}'.")
    print("One action is ready for approval; seven show distinct policy denials.")


if __name__ == "__main__":
    main()
