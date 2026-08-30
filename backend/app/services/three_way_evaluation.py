"""
Phase 23 — Three-Way Evaluation Engine.

Compares:
  TRACK_A: Deterministic EvidenceGraph baseline
  TRACK_B: TestAIProvider + EvidenceGraph
  TRACK_C: real LLM (Anthropic or OpenAI-compatible) + EvidenceGraph

With emphasis on safety metrics:
  - FALSE_SUPPORTED_RATE
  - CONTRADICTION_MISS_RATE
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.defense_types import (
    EG_DEFENSE_V1_0,
    LABEL_PRECEDENCE,
    VerificationLabel,
)
from app.models.defense_case import DefenseCase
from app.models.defense_claim import DefenseClaim
from app.models.defense_evidence_link import DefenseEvidenceLink
from app.models.evidence import EvidenceObservation
from app.models.evaluation_label import EvaluationLabel
from app.services.defense_reference_evaluator import DefenseReferenceEvaluator
from app.services.defense_verifier import DefenseVerifier
from app.services.ai_config import get_ai_config

ALL_LABELS = [
    VerificationLabel.SUPPORTED,
    VerificationLabel.INSUFFICIENT_EVIDENCE,
    VerificationLabel.CONTRADICTED,
    VerificationLabel.UNKNOWN,
]


class ThreeWayEvaluator:
    """Runs three-track evaluation and produces comparison metrics."""

    def __init__(self):
        self.baseline_evaluator = DefenseReferenceEvaluator()

    def run_all_tracks(
        self,
        db: Session,
        dataset_version: str = EG_DEFENSE_V1_0,
    ) -> dict[str, Any]:
        """Run all three evaluation tracks and return comparison."""
        cases = (
            db.query(DefenseCase)
            .filter(DefenseCase.dataset_version == dataset_version)
            .all()
        )

        if not cases:
            return {"error": "No cases found."}

        # Track A: Deterministic baseline
        track_a = self._run_track_a(db, cases)

        # Track B: Test AI + EvidenceGraph
        track_b = self._run_track_b(db, cases)

        # Track C: Real LLM + EvidenceGraph (if configured)
        track_c = self._run_track_c(db, cases)

        # Compare
        comparison = self._compare_tracks(track_a, track_b, track_c)

        return {
            "dataset_version": dataset_version,
            "total_cases": len(cases),
            "track_a_deterministic": track_a,
            "track_b_test_ai": track_b,
            "track_c_real_llm": track_c,
            "comparison": comparison,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_track_a(self, db: Session, cases: list) -> dict[str, Any]:
        """Track A: Pure deterministic baseline (Phase 21)."""
        predictions = []
        for case in cases:
            gt = self._get_ground_truth(db, case.case_id)
            result = self.baseline_evaluator.evaluate_case(db, case)
            predictions.append({
                "case_id": case.case_id,
                "expected": gt,
                "predicted": result["case_label"],
                "correct": gt == result["case_label"] if gt else None,
            })

        return self._compute_metrics(predictions, "TRACK_A_DETERMINISTIC")

    def _run_track_b(self, db: Session, cases: list) -> dict[str, Any]:
        """Track B: TestAIProvider + EvidenceGraph."""
        verifier = DefenseVerifier()
        predictions = []

        for case in cases:
            gt = self._get_ground_truth(db, case.case_id)
            defense_text = self._get_defense_text(case)

            try:
                result = verifier.verify_defense(
                    db=db,
                    case_id=case.case_id,
                    defense_text=defense_text,
                )
                predicted = result.final_decision
            except Exception:
                predicted = VerificationLabel.UNKNOWN

            predictions.append({
                "case_id": case.case_id,
                "expected": gt,
                "predicted": predicted,
                "correct": gt == predicted if gt else None,
            })

        return self._compute_metrics(predictions, "TRACK_B_TEST_AI")

    def _run_track_c(self, db: Session, cases: list) -> dict[str, Any]:
        """Track C: real LLM (Anthropic or OpenAI-compatible) + EvidenceGraph."""
        from app.services.ai_config import get_ai_config, get_ai_provider, is_real_llm_configured

        config = get_ai_config()
        if not is_real_llm_configured(config):
            return {
                "track": "TRACK_C_REAL_LLM",
                "status": "REAL_LLM_NOT_CONFIGURED",
                "provider": config.provider if config.enabled else "disabled",
                "predictions": [],
                "metrics": None,
            }

        provider = get_ai_provider(config)

        # Create a verifier with the real provider
        verifier = DefenseVerifier()
        verifier.provider = provider

        predictions = []
        for case in cases:
            gt = self._get_ground_truth(db, case.case_id)
            defense_text = self._get_defense_text(case)

            try:
                result = verifier.verify_defense(
                    db=db,
                    case_id=case.case_id,
                    defense_text=defense_text,
                )
                predicted = result.final_decision
            except Exception:
                predicted = VerificationLabel.UNKNOWN

            predictions.append({
                "case_id": case.case_id,
                "expected": gt,
                "predicted": predicted,
                "correct": gt == predicted if gt else None,
            })

        return self._compute_metrics(predictions, "TRACK_C_REAL_LLM")

    def _get_ground_truth(self, db: Session, case_id: str) -> str | None:
        gt = (
            db.query(EvaluationLabel)
            .filter(
                EvaluationLabel.case_id == case_id,
                EvaluationLabel.label_type == "GROUND_TRUTH",
            )
            .first()
        )
        return gt.label if gt else None

    def _get_defense_text(self, case: DefenseCase) -> str:
        """Generate a defense statement from case description."""
        return case.case_description or case.dispute_reason

    def _compute_metrics(
        self, predictions: list[dict], track_name: str
    ) -> dict[str, Any]:
        """Compute accuracy, per-class metrics, and safety metrics."""
        valid = [p for p in predictions if p["expected"] is not None]
        if not valid:
            return {
                "track": track_name,
                "status": "NO_VALID_PREDICTIONS",
                "predictions": predictions,
                "metrics": None,
            }

        total = len(valid)
        correct = sum(1 for p in valid if p["correct"])

        # Confusion matrix
        cm = {a: {p: 0 for p in ALL_LABELS} for a in ALL_LABELS}
        for p in valid:
            cm[p["expected"]][p["predicted"]] += 1

        # Per-class metrics
        per_class = {}
        for label in ALL_LABELS:
            tp = cm[label][label]
            fp = sum(cm[other][label] for other in ALL_LABELS if other != label)
            fn = sum(cm[label][other] for other in ALL_LABELS if other != label)
            support = sum(cm[label][other] for other in ALL_LABELS)

            precision = tp / (tp + fp) if (tp + fp) > 0 else None
            recall = tp / (tp + fn) if (tp + fn) > 0 else None
            f1 = (
                (2 * precision * recall / (precision + recall))
                if precision and recall and (precision + recall) > 0
                else None
            )

            per_class[label] = {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": support,
            }

        # Safety metrics
        false_supported = sum(
            1 for p in valid
            if p["predicted"] == "SUPPORTED" and p["expected"] != "SUPPORTED"
        )
        false_supported_rate = false_supported / total if total > 0 else 0

        contradiction_misses = sum(
            1 for p in valid
            if p["expected"] == "CONTRADICTED" and p["predicted"] != "CONTRADICTED"
        )
        contradiction_miss_rate = (
            contradiction_misses / sum(1 for p in valid if p["expected"] == "CONTRADICTED")
            if sum(1 for p in valid if p["expected"] == "CONTRADICTED") > 0
            else 0
        )

        # Macro averages
        precisions = [v["precision"] for v in per_class.values() if v["precision"] is not None]
        recalls = [v["recall"] for v in per_class.values() if v["recall"] is not None]
        f1s = [v["f1"] for v in per_class.values() if v["f1"] is not None]

        return {
            "track": track_name,
            "status": "COMPLETED",
            "total_cases": total,
            "correct": correct,
            "accuracy": correct / total if total > 0 else 0,
            "macro_precision": sum(precisions) / len(precisions) if precisions else 0,
            "macro_recall": sum(recalls) / len(recalls) if recalls else 0,
            "macro_f1": sum(f1s) / len(f1s) if f1s else 0,
            "per_class": per_class,
            "confusion_matrix": cm,
            "safety": {
                "false_supported_count": false_supported,
                "false_supported_rate": false_supported_rate,
                "contradiction_misses": contradiction_misses,
                "contradiction_miss_rate": contradiction_miss_rate,
            },
            "false_supported_cases": [
                p for p in valid
                if p["predicted"] == "SUPPORTED" and p["expected"] != "SUPPORTED"
            ],
            "predictions": predictions,
        }

    def _compare_tracks(
        self,
        track_a: dict,
        track_b: dict,
        track_c: dict,
    ) -> dict[str, Any]:
        """Create comparison summary."""
        comparison = {
            "accuracy": {},
            "macro_f1": {},
            "false_supported_rate": {},
            "contradiction_miss_rate": {},
            "improvement_from_baseline": {},
        }

        a_acc = track_a.get("accuracy", 0)
        b_acc = track_b.get("accuracy", 0)
        c_acc = track_c.get("accuracy", 0) if track_c.get("status") == "COMPLETED" else None

        comparison["accuracy"] = {
            "deterministic": a_acc,
            "test_ai": b_acc,
            "real_llm": c_acc,
        }
        comparison["macro_f1"] = {
            "deterministic": track_a.get("macro_f1", 0),
            "test_ai": track_b.get("macro_f1", 0),
            "real_llm": track_c.get("macro_f1") if track_c.get("status") == "COMPLETED" else None,
        }

        a_fsr = track_a.get("safety", {}).get("false_supported_rate", 0)
        b_fsr = track_b.get("safety", {}).get("false_supported_rate", 0)
        c_fsr = track_c.get("safety", {}).get("false_supported_rate", 0) if track_c.get("status") == "COMPLETED" else None

        comparison["false_supported_rate"] = {
            "deterministic": a_fsr,
            "test_ai": b_fsr,
            "real_llm": c_fsr,
            "safer_is_lower": True,
        }

        comparison["improvement_from_baseline"] = {
            "test_ai_vs_deterministic": {
                "accuracy_delta": b_acc - a_acc,
                "f1_delta": track_b.get("macro_f1", 0) - track_a.get("macro_f1", 0),
            },
        }

        if c_acc is not None:
            comparison["improvement_from_baseline"]["real_llm_vs_deterministic"] = {
                "accuracy_delta": c_acc - a_acc,
                "f1_delta": track_c.get("macro_f1", 0) - track_a.get("macro_f1", 0),
            }

        return comparison
