"""
API v1 router — aggregates all v1 route modules.
"""

from fastapi import APIRouter

from app.api.v1.evidence import router as evidence_router
from app.api.v1.graph import router as graph_router
from app.api.v1.health import router as health_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.integrity import router as integrity_router
from app.api.v1.orders import router as orders_router
from app.api.v1.payments import router as payments_router
from app.api.v1.quality import router as quality_router
from app.api.v1.structure import router as structure_router
from app.api.v1.conflicts import router as conflicts_router
from app.api.v1.traces import router as traces_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.evolution import router as evolution_router
from app.api.v1.investigation import router as investigation_router
from app.api.v1.reconciliation import router as reconciliation_router
from app.api.v1.lineage import router as lineage_router
from app.api.v1.coverage import router as coverage_router
from app.api.v1.reliability import router as reliability_router
from app.api.v1.decision_replay import router as decision_replay_router
from app.api.v1.operations import router as operations_router, payment_ops_router
# Phase 20 — New features
from app.api.v1.live_stream import router as live_stream_router
from app.api.v1.risk_score import router as risk_score_router
from app.api.v1.fraud_detection import router as fraud_detection_router
from app.api.v1.investigation_center import router as investigation_center_router
from app.api.v1.payment_analytics import router as payment_analytics_router
from app.api.v1.defense_evaluation import router as defense_evaluation_router
from app.api.v1.defense_verification import router as defense_verification_router
from app.api.v1.defense_ai_evaluation import router as defense_ai_evaluation_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router, prefix="/health")
router.include_router(operations_router, prefix="")
router.include_router(payment_ops_router, prefix="")
router.include_router(webhooks_router, prefix="/webhooks")
router.include_router(integrations_router, prefix="/integrations")
router.include_router(payments_router, prefix="/payments")
router.include_router(orders_router, prefix="/orders")
router.include_router(evidence_router, prefix="/evidence")
router.include_router(graph_router, prefix="/graph")
router.include_router(quality_router, prefix="/quality")
router.include_router(structure_router, prefix="")
router.include_router(conflicts_router, prefix="")
router.include_router(integrity_router, prefix="")
router.include_router(traces_router, prefix="")
router.include_router(evolution_router, prefix="")
router.include_router(investigation_router, prefix="")
router.include_router(reconciliation_router, prefix="")
router.include_router(lineage_router, prefix="")
router.include_router(coverage_router, prefix="")
router.include_router(reliability_router, prefix="")
router.include_router(decision_replay_router, prefix="")
# Phase 20 — New feature routers
router.include_router(live_stream_router, prefix="")
router.include_router(risk_score_router, prefix="")
router.include_router(fraud_detection_router, prefix="")
router.include_router(investigation_center_router, prefix="")
router.include_router(payment_analytics_router, prefix="")
# Phase 21 — Defense Verification Evaluation
router.include_router(defense_evaluation_router, prefix="")
router.include_router(defense_verification_router, prefix="")
router.include_router(defense_ai_evaluation_router, prefix="")
