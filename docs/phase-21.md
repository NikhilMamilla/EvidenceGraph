# Phase 21 — Defense Verification Evaluation Foundation

## Objective

Establish a scientifically defensible evaluation environment for verifying whether a merchant's chargeback defense claim is supported by available evidence. This phase does NOT implement AI. It creates the ground truth, deterministic baseline, evaluation dataset, and metrics framework against which AI will later be measured.

## Why Delivery Disputes

Delivery/merchandise-not-received disputes were selected because:

1. **Clear evidence requirements** — delivery proof, tracking, signature are well-defined
2. **Deterministic verification** — delivery status can be verified from transactional data
3. **Measurable** — evidence presence/absence/timing is binary or timestamp-based
4. **Narrow scope** — avoids multi-dispute complexity in Phase 21

## Scope

- Defense verification for DELIVERY_NOT_RECEIVED disputes only
- Deterministic reference evaluator (no AI)
- 20+ golden test cases
- Metamorphic and adversarial tests
- Evaluation metrics (precision, recall, F1, confusion matrix)
- Dataset versioning and provenance
- Frozen test set protocol

## Non-Goals

- AI/LLM implementation (Phase 22)
- Real chargeback data ingestion
- Production deployment
- Multi-dispute-type support
- Automated defense submission

## Dataset Philosophy

Every evaluation case must be classified as:

- **REAL_RAZORPAY_TEST_DATA** — Real Razorpay Test Mode events used as base
- **CONTROLLED_TEST_CASE** — Real events + documented deterministic transformations
- **SYNTHETIC_CASE** — Generated from domain constraints, clearly marked
- **HUMAN_LABELED_CASE** — Expert-annotated ground truth

No dataset item may be mislabeled as "real historical chargeback data" when it is not.

## Label Taxonomy

| Label | Definition |
|-------|-----------|
| SUPPORTED | Claim materially supported by authoritative, temporally valid, non-conflicting, independent evidence |
| INSUFFICIENT_EVIDENCE | No contradiction, but required evidence absent or insufficient |
| CONTRADICTED | At least one authoritative evidence source conflicts with the claim |
| UNKNOWN | Insufficient information to determine support or contradiction |

### Label Precedence (Deterministic)

When multiple signals conflict, apply this precedence:

1. CONTRADICTED (authoritative contradiction always wins)
2. SUPPORTED (complete evidence with no contradictions)
3. INSUFFICIENT_EVIDENCE (missing required evidence, no contradiction)
4. UNKNOWN (insufficient information to classify)

## Evaluation Methodology

1. Load frozen dataset
2. Run deterministic reference evaluator on each case
3. Compare prediction vs expected label
4. Compute confusion matrix, precision, recall, F1
5. Report per-class metrics
6. Identify and classify errors

## Baseline

The deterministic reference evaluator IS the baseline. Future AI must outperform it on a meaningful metric.

## Metrics

- Accuracy (reported, not sole metric)
- Macro Precision, Recall, F1 (primary)
- Per-class Precision, Recall
- Confusion Matrix
- False-Supported Rate
- Contradiction Recall

## Limitations

- This is NOT a historical Razorpay chargeback dataset
- Test Mode payments are NOT real chargeback outcomes
- Controlled cases are NOT real merchant disputes
- Small evaluation sets have wide uncertainty
- Phase 21 does NOT prove production AI performance
- No LLM is implemented
- No AI precision/recall is claimed

## What Phase 22 Will Build

- LLM-based claim extraction
- Semantic evidence-claim matching
- AI + deterministic hybrid verification
- Expanded evaluation dataset
- Production-grade metrics with confidence intervals
