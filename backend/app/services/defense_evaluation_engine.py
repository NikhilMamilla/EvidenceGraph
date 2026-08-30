"""
Phase 21 — Baseline Evaluation Engine.

Runs the deterministic reference evaluator against a frozen dataset,
computes confusion matrix, precision, recall, F1, and per-class metrics.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.defense_types import (
    DEFENSE_VERIFICATION_METHODOLOGY_V1,
    EG_DEFENSE_V1_0,
    LABEL_PRECEDENCE,
    VerificationLabel,
)
from app.models.defense_case import DefenseCase
from app.models.evaluation_label import EvaluationLabel
from app.models.evaluation_dataset import EvaluationDataset
from app.models.evaluation_run import EvaluationRun
from app.services.defense_reference_evaluator import (
    REF_EVAL_METHODOLOGY_VERSION,
    DefenseReferenceEvaluator,
)

ALL_LABELS = [
    VerificationLabel.SUPPORTED,
    VerificationLabel.INSUFFICIENT_EVIDENCE,
    VerificationLabel.CONTRADICTED,
    VerificationLabel.UNKNOWN,
]


class DefenseEvaluationEngine:
    """Runs evaluation and computes metrics."""

    def __init__(self):
        self.evaluator = DefenseReferenceEvaluator()

    def run_evaluation(
        self,
        db: Session,
        dataset_version: str = EG_DEFENSE_V1_0,
        evaluation_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Run a full evaluation against the specified dataset version."""

        run_id = f"RUN_{uuid.uuid4().hex[:12].upper()}"

        # Get dataset
        dataset = (
            db.query(EvaluationDataset)
            .filter(EvaluationDataset.dataset_version == dataset_version)
            .first()
        )
        if not dataset:
            return {"error": f"Dataset {dataset_version} not found."}

        # Get all cases for this dataset
        cases = (
            db.query(DefenseCase)
            .filter(DefenseCase.dataset_version == dataset_version)
            .all()
        )

        if not cases:
            return {"error": "No cases found in dataset."}

        # Evaluate each case
        predictions = []
        error_cases = []
        correct = 0

        for case in cases:
            # Get ground truth
            gt_label = (
                db.query(EvaluationLabel)
                .filter(
                    EvaluationLabel.case_id == case.case_id,
                    EvaluationLabel.dataset_version == dataset_version,
                    EvaluationLabel.label_type == "GROUND_TRUTH",
                )
                .first()
            )

            if not gt_label:
                error_cases.append({
                    "case_id": case.case_id,
                    "error": "No ground truth label found.",
                })
                continue

            # Run deterministic evaluator
            eval_result = self.evaluator.evaluate_case(db, case, evaluation_time)
            predicted_label = eval_result["case_label"]
            expected_label = gt_label.label

            is_correct = predicted_label == expected_label
            if is_correct:
                correct += 1

            prediction = {
                "case_id": case.case_id,
                "expected": expected_label,
                "predicted": predicted_label,
                "correct": is_correct,
                "rationale": eval_result.get("rationale", ""),
                "claim_results": eval_result.get("claim_results", []),
            }
            predictions.append(prediction)

            if not is_correct:
                error_cases.append({
                    "case_id": case.case_id,
                    "expected": expected_label,
                    "predicted": predicted_label,
                    "rationale": eval_result.get("rationale", ""),
                })

        # Compute confusion matrix
        confusion_matrix = self._compute_confusion_matrix(predictions)

        # Compute metrics
        metrics = self._compute_metrics(confusion_matrix, predictions)

        # Compute results fingerprint
        results_fingerprint = self._compute_results_fingerprint(
            dataset.dataset_fingerprint, predictions, metrics
        )

        # Save run
        run = EvaluationRun(
            run_id=run_id,
            dataset_version=dataset_version,
            methodology_version=(
                f"{DEFENSE_VERIFICATION_METHODOLOGY_V1}+{REF_EVAL_METHODOLOGY_VERSION}"
            ),
            status="COMPLETED",
            total_cases=len(cases),
            evaluated_cases=len(predictions),
            correct_predictions=correct,
            confusion_matrix=confusion_matrix,
            metrics=metrics,
            error_cases=error_cases,
            results_fingerprint=results_fingerprint,
            dataset_fingerprint=dataset.dataset_fingerprint,
        )
        db.add(run)
        db.commit()

        return {
            "run_id": run_id,
            "dataset_version": dataset_version,
            "reference_evaluator_version": REF_EVAL_METHODOLOGY_VERSION,
            "total_cases": len(cases),
            "evaluated_cases": len(predictions),
            "correct_predictions": correct,
            "accuracy": metrics.get("accuracy", 0),
            "macro_f1": metrics.get("macro_f1", 0),
            "confusion_matrix": confusion_matrix,
            "per_class_metrics": metrics.get("per_class", {}),
            "error_cases": error_cases,
            "results_fingerprint": results_fingerprint,
        }

    def _compute_confusion_matrix(self, predictions: list[dict]) -> dict:
        """Build confusion matrix from predictions."""
        matrix = {actual: {pred: 0 for pred in ALL_LABELS} for actual in ALL_LABELS}

        for p in predictions:
            expected = p["expected"]
            predicted = p["predicted"]
            if expected in matrix and predicted in matrix[expected]:
                matrix[expected][predicted] += 1

        return matrix

    def _compute_metrics(
        self, confusion_matrix: dict, predictions: list[dict]
    ) -> dict[str, Any]:
        """Compute accuracy, precision, recall, F1, per-class metrics."""

        total = sum(
            confusion_matrix[a][p]
            for a in ALL_LABELS
            for p in ALL_LABELS
        )
        correct = sum(
            confusion_matrix[a][a] for a in ALL_LABELS
        )

        accuracy = correct / total if total > 0 else 0

        per_class = {}
        precisions = []
        recalls = []
        f1s = []

        for label in ALL_LABELS:
            tp = confusion_matrix[label][label]
            fp = sum(confusion_matrix[other][label] for other in ALL_LABELS if other != label)
            fn = sum(confusion_matrix[label][other] for other in ALL_LABELS if other != label)
            support = sum(confusion_matrix[label][other] for other in ALL_LABELS)

            precision = tp / (tp + fp) if (tp + fp) > 0 else None
            recall = tp / (tp + fn) if (tp + fn) > 0 else None
            f1 = (
                (2 * precision * recall / (precision + recall))
                if (precision is not None and recall is not None and (precision + recall) > 0)
                else None
            )

            per_class[label] = {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": support,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }

            if precision is not None:
                precisions.append(precision)
            if recall is not None:
                recalls.append(recall)
            if f1 is not None:
                f1s.append(f1)

        macro_precision = sum(precisions) / len(precisions) if precisions else 0
        macro_recall = sum(recalls) / len(recalls) if recalls else 0
        macro_f1 = sum(f1s) / len(f1s) if f1s else 0

        return {
            "accuracy": accuracy,
            "macro_precision": macro_precision,
            "macro_recall": macro_recall,
            "macro_f1": macro_f1,
            "per_class": per_class,
            "total_samples": total,
        }

    def _compute_results_fingerprint(
        self,
        dataset_fingerprint: str,
        predictions: list[dict],
        metrics: dict,
    ) -> str:
        """Compute deterministic hash of evaluation results."""
        content = json.dumps(
            {
                "dataset_fingerprint": dataset_fingerprint,
                "methodology": DEFENSE_VERIFICATION_METHODOLOGY_V1,
                "predictions": [
                    {"case_id": p["case_id"], "expected": p["expected"], "predicted": p["predicted"]}
                    for p in sorted(predictions, key=lambda x: x["case_id"])
                ],
                "metrics": {
                    "accuracy": metrics.get("accuracy"),
                    "macro_f1": metrics.get("macro_f1"),
                },
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()
