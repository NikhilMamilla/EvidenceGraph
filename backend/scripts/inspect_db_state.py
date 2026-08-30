"""Phase 10 verification helper — inspect real DB state (read-only)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text

from app.db.session import get_session_factory

QUERIES = [
    ("webhook_events", "select count(*) from webhook_events"),
    ("payments", "select razorpay_payment_id, status, amount_minor, currency from payments"),
    ("evidence", "select count(*) from evidence_observations"),
    ("quality_snaps", "select count(*) from evidence_quality_snapshots"),
    ("structure_snaps", "select count(*) from evidence_structure_snapshots"),
    ("conflicts", "select count(*) from evidence_conflicts"),
    ("integrity_snapshots", "select payment_id, overall_status, evaluated_at from evidence_integrity_snapshots order by evaluated_at"),
    ("traces", "select trace_id, payment_id, status, overall_status from evidence_integrity_traces"),
    (
        "events_detail",
        "select id, razorpay_event_id, event_type, processing_status, payment_id "
        "from webhook_events order by id",
    ),
]

def main():
    db = get_session_factory()()
    try:
        for label, query in QUERIES:
            try:
                rows = db.execute(text(query)).fetchall()
                print(label, "->", [tuple(r) for r in rows][:12])
            except Exception as exc:  # noqa: BLE001
                print(label, "ERR", type(exc).__name__, str(exc)[:120])
    finally:
        db.close()

if __name__ == "__main__":
    main()
