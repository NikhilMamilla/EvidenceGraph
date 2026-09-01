#!/bin/sh
# =============================================================================
# EvidenceGraph backend entrypoint
# Wait for the database, run schema migrations, then start the API.
# =============================================================================
set -e

echo "[entrypoint] checking database connectivity..."
if ! python scripts/wait_for_db.py; then
    echo "[entrypoint] database unreachable — see the checklist above. Exiting."
    exit 1
fi

echo "[entrypoint] applying database migrations (alembic upgrade head)..."
alembic upgrade head
echo "[entrypoint] migrations complete."

# Optional: seed the 20 golden delivery-dispute cases on first boot.
# seed_golden_cases() is idempotent (skips cases that already exist).
if [ "${SEED_GOLDEN_CASES:-false}" = "true" ]; then
    echo "[entrypoint] seeding golden defense cases..."
    python scripts/seed_defense_dataset.py || echo "[entrypoint] seed failed (non-fatal), continuing."
fi

echo "[entrypoint] starting uvicorn on 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
