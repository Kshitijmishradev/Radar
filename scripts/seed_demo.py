"""Reset every recording-ready dataset used by the Radar dashboards.

Run with: .venv/bin/python -m scripts.seed_demo
"""

from __future__ import annotations

from scripts.seed_ai_demo import main as seed_ai_demo
from scripts.seed_video_demo import main as seed_cloud_demo


def main() -> None:
    print("Resetting the Radar Video Demo tenant…")
    seed_cloud_demo()
    seed_ai_demo()
    print("Demo ready: sign in as Alex (Operator), Priya (Approver), or Maya (Admin).")


if __name__ == "__main__":
    main()
