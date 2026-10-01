"""Run a standalone local worker: python -m app.worker."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.domain import RemediationService, Repository
from app.jobs import RemediationWorker


def main() -> None:
    database_path = os.getenv("DATABASE_PATH", str(Path("data") / "radar.db"))
    repository = Repository(database_path)
    worker = RemediationWorker(repository, RemediationService(repository))
    print("Remediation worker started. Press Ctrl+C to stop.")
    try:
        while True:
            outcome = worker.process_next()
            if outcome:
                print(f"Job {outcome.job['id']} → {outcome.job['status']}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Remediation worker stopped.")


if __name__ == "__main__":
    main()
