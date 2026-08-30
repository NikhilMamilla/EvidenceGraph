"""
Seed the golden delivery-dispute dataset (EG-DEFENSE-1.0) into the database.

Idempotent: seed_golden_cases() skips any case that already exists.

Usage (from backend/):
    python scripts/seed_defense_dataset.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import get_session_factory
from app.services.golden_test_cases import seed_golden_cases


def main() -> None:
    db = get_session_factory()()
    try:
        summary = seed_golden_cases(db)
        print("[seed] dataset:", summary.get("dataset_version"))
        print("[seed] cases created:", summary.get("cases_created"))
        print("[seed] label distribution:", summary.get("label_distribution"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
