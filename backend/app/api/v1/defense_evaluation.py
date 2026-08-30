"""
Phase 21 — Defense Evaluation API.

Exposes dataset management, golden case seeding, evaluation runs,
and results for the defense verification evaluation framework.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.defense_types import EG_DEFENSE_V1_0
from app.models.defense_case import DefenseCase
from app.models.defense_claim import DefenseClaim
from app.models.defense_evidence_link import DefenseEvidenceLink
from app.models.evaluation_label import EvaluationLabel
from app.models.evaluation_dataset import EvaluationDataset
from app.models.evaluation_run import EvaluationRun
from app.services.golden_test_cases import seed_golden_cases
from app.services.defense_evaluation_engine import DefenseEvaluationEngine

router = APIRouter(prefix="/defense", tags=["Phase 21 — Defense Evaluation"])


class SeedRequest(BaseModel):
    dataset_version: str = EG_DEFENSE_V1_0


class EvaluateRequest(BaseModel):
    dataset_version: str = EG_DEFENSE_V1_0


# ---------------------------------------------------------------------------
# Dataset endpoints
# ---------------------------------------------------------------------------

@router.get("/evaluation/datasets")
def list_datasets(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List all evaluation dataset versions."""
    datasets = db.query(EvaluationDataset).all()
    return [
        {
            "dataset_version": d.dataset_version,
            "total_cases": d.total_cases,
            "is_frozen": d.is_frozen,
            "source_counts": d.source_counts,
            "label_counts": d.label_counts,
            "split_counts": d.split_counts,
            "dataset_fingerprint": d.dataset_fingerprint,
            "methodology_version": d.methodology_version,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in datasets
    ]


@router.get("/evaluation/datasets/{dataset_version}")
def get_dataset(dataset_version: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get a specific dataset version with full details."""
    dataset = (
        db.query(EvaluationDataset)
        .filter(EvaluationDataset.dataset_version == dataset_version)
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_version} not found.")

    cases = (
        db.query(DefenseCase)
        .filter(DefenseCase.dataset_version == dataset_version)
        .all()
    )

    return {
        "dataset_version": dataset.dataset_version,
        "total_cases": dataset.total_cases,
        "is_frozen": dataset.is_frozen,
        "source_counts": dataset.source_counts,
        "label_counts": dataset.label_counts,
        "split_counts": dataset.split_counts,
        "dataset_fingerprint": dataset.dataset_fingerprint,
        "methodology_version": dataset.methodology_version,
        "cases": [
            {
                "case_id": c.case_id,
                "dispute_category": c.dispute_category,
                "dispute_reason": c.dispute_reason,
                "case_source": c.case_source,
                "status": c.status,
            }
            for c in cases
        ],
    }


# ---------------------------------------------------------------------------
# Case endpoints
# ---------------------------------------------------------------------------

@router.get("/evaluation/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get a specific defense case with claims and evidence links."""
    case = db.query(DefenseCase).filter(DefenseCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    claims = (
        db.query(DefenseClaim).filter(DefenseClaim.case_id == case_id).all()
    )

    claim_details = []
    for claim in claims:
        links = (
            db.query(DefenseEvidenceLink)
            .filter(DefenseEvidenceLink.claim_id == claim.claim_id)
            .all()
        )
        claim_details.append({
            "claim_id": claim.claim_id,
            "claim_text": claim.claim_text,
            "claim_type": claim.claim_type,
            "evidence_links": [
                {
                    "evidence_observation_id": l.evidence_observation_id,
                    "link_type": l.link_type,
                    "relevance_score": l.relevance_score,
                }
                for l in links
            ],
        })

    ground_truth = (
        db.query(EvaluationLabel)
        .filter(
            EvaluationLabel.case_id == case_id,
            EvaluationLabel.label_type == "GROUND_TRUTH",
        )
        .first()
    )

    return {
        "case_id": case.case_id,
        "dispute_category": case.dispute_category,
        "dispute_reason": case.dispute_reason,
        "case_description": case.case_description,
        "payment_reference": case.payment_reference,
        "order_reference": case.order_reference,
        "dataset_version": case.dataset_version,
        "case_source": case.case_source,
        "status": case.status,
        "claims": claim_details,
        "ground_truth": {
            "label": ground_truth.label if ground_truth else None,
            "rationale": ground_truth.rationale if ground_truth else None,
        } if ground_truth else None,
    }


@router.get("/evaluation/cases/{case_id}/trace")
def get_case_trace(case_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get full evaluation trace for a case — claim-level predictions and evidence references."""
    case = db.query(DefenseCase).filter(DefenseCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    evaluator = DefenseEvaluationEngine()
    eval_result = evaluator.evaluator.evaluate_case(db, case)

    return {
        "case_id": case_id,
        "evaluation": eval_result,
        "methodology_version": "DEFENSE_VERIFICATION_METHODOLOGY_V1",
    }


# ---------------------------------------------------------------------------
# Seed & evaluate endpoints
# ---------------------------------------------------------------------------

@router.post("/evaluation/seed")
def seed_dataset(
    request: SeedRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Seed golden test cases into the specified dataset version."""
    result = seed_golden_cases(db)
    return result


@router.post("/evaluation/run")
def run_evaluation(
    request: EvaluateRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run evaluation against a dataset version."""
    dataset_version = request.dataset_version if request else EG_DEFENSE_V1_0
    engine = DefenseEvaluationEngine()
    result = engine.run_evaluation(db, dataset_version=dataset_version)
    return result


@router.get("/evaluation/results/{run_id}")
def get_run_results(run_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get results of a specific evaluation run."""
    run = db.query(EvaluationRun).filter(EvaluationRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    return {
        "run_id": run.run_id,
        "dataset_version": run.dataset_version,
        "methodology_version": run.methodology_version,
        "status": run.status,
        "total_cases": run.total_cases,
        "evaluated_cases": run.evaluated_cases,
        "correct_predictions": run.correct_predictions,
        "accuracy": run.correct_predictions / run.evaluated_cases if run.evaluated_cases else 0,
        "confusion_matrix": run.confusion_matrix,
        "metrics": run.metrics,
        "error_cases": run.error_cases,
        "results_fingerprint": run.results_fingerprint,
        "dataset_fingerprint": run.dataset_fingerprint,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@router.get("/evaluation/runs")
def list_runs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List all evaluation runs."""
    runs = db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).all()
    return [
        {
            "run_id": r.run_id,
            "dataset_version": r.dataset_version,
            "status": r.status,
            "total_cases": r.total_cases,
            "evaluated_cases": r.evaluated_cases,
            "correct_predictions": r.correct_predictions,
            "accuracy": r.correct_predictions / r.evaluated_cases if r.evaluated_cases else 0,
            "macro_f1": r.metrics.get("macro_f1") if r.metrics else None,
            "results_fingerprint": r.results_fingerprint,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]
