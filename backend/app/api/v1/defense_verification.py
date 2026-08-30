"""
Phase 22 — Defense Verification API.

Exposes AI-enhanced defense verification endpoints.
AI semantic layer + deterministic EvidenceGraph = final verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.defense_case import DefenseCase
from app.models.defense_types import EG_DEFENSE_V1_0
from app.services.defense_verifier import DefenseVerifier
from app.services.ai_config import get_ai_config, get_ai_provider, is_real_llm_configured

router = APIRouter(prefix="/defense", tags=["Phase 22 — AI Defense Verification"])


class VerifyDefenseRequest(BaseModel):
    case_id: str = Field(..., description="Defense case ID to verify")
    defense_text: str = Field(..., description="Merchant's defense statement text")
    evaluation_time: str | None = Field(
        default=None,
        description="ISO timestamp for evaluation point (default: now)",
    )


@router.post("/verify")
def verify_defense(
    request: VerifyDefenseRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Full AI-enhanced defense verification pipeline.

    1. AI extracts claims from defense text
    2. Candidate evidence retrieved deterministically
    3. AI matches claims to evidence
    4. EvidenceGraph performs factual verification
    5. Final decision returned
    """
    # Parse evaluation time
    eval_time = None
    if request.evaluation_time:
        eval_time = datetime.fromisoformat(request.evaluation_time)

    # Check case exists
    case = db.query(DefenseCase).filter(DefenseCase.case_id == request.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {request.case_id} not found.")

    # Run verification
    verifier = DefenseVerifier()
    result = verifier.verify_defense(
        db=db,
        case_id=request.case_id,
        defense_text=request.defense_text,
        evaluation_time=eval_time,
    )

    return result.model_dump()


@router.get("/ai/status")
def ai_status() -> dict[str, Any]:
    """Check AI provider status."""
    config = get_ai_config()
    provider = get_ai_provider(config)
    real_ready = is_real_llm_configured(config)
    provider_kind = (
        "REAL_LLM" if config.enabled and config.provider in ("openai", "anthropic")
        else ("TEST" if config.enabled else "DISABLED")
    )
    return {
        "enabled": config.enabled,
        "provider": config.provider if config.enabled else "disabled",
        "provider_name": getattr(provider, "provider_name", "UNKNOWN"),
        "provider_kind": provider_kind,
        "model": getattr(provider, "model", None) if config.enabled else None,
        "real_llm_ready": real_ready,
        "status": (
            "REAL_LLM_READY" if real_ready
            else "REAL_LLM_NOT_CONFIGURED" if provider_kind == "REAL_LLM"
            else "TEST_PROVIDER" if config.enabled
            else "NOT_CONFIGURED"
        ),
    }


@router.get("/cases/{case_id}/analysis")
def get_case_analysis(
    case_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Get existing analysis results for a case.
    Returns claims, evidence links, and deterministic evaluation.
    """
    from app.models.defense_claim import DefenseClaim
    from app.models.defense_evidence_link import DefenseEvidenceLink
    from app.services.defense_reference_evaluator import DefenseReferenceEvaluator

    case = db.query(DefenseCase).filter(DefenseCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    claims = db.query(DefenseClaim).filter(DefenseClaim.case_id == case_id).all()
    claim_details = []
    for claim in claims:
        links = (
            db.query(DefenseEvidenceLink)
            .filter(DefenseEvidenceLink.claim_id == claim.claim_id)
            .all()
        )
        claim_details.append({
            "claim_id": claim.claim_id,
            "claim_type": claim.claim_type,
            "claim_text": claim.claim_text,
            "evidence_links": [
                {
                    "evidence_id": l.evidence_observation_id,
                    "link_type": l.link_type,
                    "relevance_score": l.relevance_score,
                }
                for l in links
            ],
        })

    # Run deterministic evaluation
    evaluator = DefenseReferenceEvaluator()
    det_result = evaluator.evaluate_case(db, case)

    return {
        "case_id": case_id,
        "claims": claim_details,
        "deterministic_result": det_result,
    }
