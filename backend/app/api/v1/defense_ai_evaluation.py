"""
Phase 23 — Defense AI Evaluation API.

Three-way comparison, safety metrics, false-supported analysis.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.defense_types import EG_DEFENSE_V1_0
from app.services.three_way_evaluation import ThreeWayEvaluator
from app.services.ai_config import get_ai_config

router = APIRouter(prefix="/defense/ai", tags=["Phase 23 — AI Evaluation"])


class EvaluateRequest(BaseModel):
    dataset_version: str = EG_DEFENSE_V1_0


@router.get("/config")
def get_ai_config_status() -> dict[str, Any]:
    """Get AI provider configuration status."""
    config = get_ai_config()
    return {
        "enabled": config.enabled,
        "provider": config.provider if config.enabled else "disabled",
        "model": config.model if config.enabled else None,
        "provider_type": "TEST" if config.provider == "test" else (
            "REAL_LLM" if config.enabled else "DISABLED"
        ),
        "status": "CONFIGURED" if config.enabled else "NOT_CONFIGURED",
    }


@router.post("/evaluate")
def run_three_way_evaluation(
    request: EvaluateRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run three-way evaluation: Deterministic vs Test AI vs Real LLM."""
    dataset_version = request.dataset_version if request else EG_DEFENSE_V1_0
    evaluator = ThreeWayEvaluator()
    return evaluator.run_all_tracks(db, dataset_version=dataset_version)


@router.get("/safety")
def get_safety_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get safety-focused summary of all evaluations."""
    evaluator = ThreeWayEvaluator()
    result = evaluator.run_all_tracks(db)

    if "error" in result:
        return result

    track_a = result.get("track_a_deterministic", {})
    track_b = result.get("track_b_test_ai", {})

    return {
        "safety_summary": {
            "deterministic": {
                "false_supported_rate": track_a.get("safety", {}).get("false_supported_rate", 0),
                "contradiction_miss_rate": track_a.get("safety", {}).get("contradiction_miss_rate", 0),
            },
            "test_ai": {
                "false_supported_rate": track_b.get("safety", {}).get("false_supported_rate", 0),
                "contradiction_miss_rate": track_b.get("safety", {}).get("contradiction_miss_rate", 0),
            },
            "real_llm": {
                "status": result.get("track_c_real_llm", {}).get("status", "NOT_RUN"),
                "false_supported_rate": result.get("track_c_real_llm", {}).get("safety", {}).get("false_supported_rate"),
            },
        },
        "false_supported_cases": {
            "deterministic": track_a.get("false_supported_cases", []),
            "test_ai": track_b.get("false_supported_cases", []),
        },
    }


@router.get("/compare")
def compare_tracks(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get side-by-side comparison of all three tracks."""
    evaluator = ThreeWayEvaluator()
    result = evaluator.run_all_tracks(db)
    return result.get("comparison", {})
