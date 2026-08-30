# Phase 6: Evidence Quality Measurement & Temporal Reliability

## 1. Objective
Phase 6 introduces the measurement layer for evidence quality. It establishes three fundamental, deterministic, and versioned properties of evidence: **Freshness**, **Historical Reliability Status**, and **Source Quality** (Authority & Directness).
Crucially, Phase 6 **does not** create a composite "Evidence Integrity Score" or fraud/risk score. It provides explainable, deterministic, and versioned structural measurements derived from real observations.

## 2. Freshness Measurement
Evidence freshness reflects the temporal decay of an observation's informational value relative to an evaluation time.

### Age Calculation
Freshness is calculated from the time the underlying fact was actually observed (`observed_at`), **not** when it was ingested (`created_at`) or processed:
$$\text{Age} = \text{evaluation\_time} - \text{observed\_at}$$
All calculations require timezone-aware UTC timestamps. If `observed_at` is missing or in the future relative to `evaluation_time`, freshness resolves to `UNKNOWN`.

### Evaluation Timestamp
The evaluation timestamp is an explicit parameter passed to the evaluation engine (defaulting to the current UTC timestamp). This allows deterministic historical backtesting and temporal re-evaluation.

### Freshness Policy
Different evidence types have different rates of informational decay:
*   `PAYMENT_STATUS`: Current < 1 hour, Aging < 24 hours, Stale ≥ 24 hours.
*   `PAYMENT_EVENT`: Current < 6 hours, Aging < 48 hours, Stale ≥ 48 hours.
*   `PAYMENT_METHOD`: Current < 30 days, Aging < 90 days, Stale ≥ 90 days.
*   `PAYMENT_AMOUNT`: Current < 365 days, Aging < 730 days, Stale ≥ 730 days.
*   `PAYMENT_CURRENCY`: Current < 365 days, Aging < 730 days, Stale ≥ 730 days.

### Freshness States
*   `CURRENT`: The observation is fresh and within the active validity window.
*   `AGING`: The observation is past its primary freshness window but not yet obsolete.
*   `STALE`: The observation is old and should be treated with lower confidence.
*   `UNKNOWN`: The observation timestamp is invalid, absent, or future-dated.

## 3. Source Metadata & Authority

Source quality is structural and declarative, not a speculative trust score.

### Source Types
*   `RAZORPAY_WEBHOOK`: Ingested webhook delivery from Razorpay.
*   `RAZORPAY_API`: Direct synchronous API call to Razorpay (where available).
*   `INTERNAL_SYSTEM`: System-generated canonical models and derivations.

### Authority Representation
Defined in `EvidenceSourceProfile` taxonomy:
*   `PRIMARY`: The authoritative system of record for the event (e.g., Razorpay webhook for `PAYMENT_EVENT`).
*   `SECONDARY`: Intermediary or derived system observation (e.g., internal system recording payment status).
*   `TERTIARY`: Third-party or indirect reporting.
*   `UNKNOWN`: Unclassified source.

### Source Directness
*   `DIRECT`: Observation reported first-hand by the authoritative source.
*   `DERIVED`: Computed or normalized from raw payload fields.
*   `INFERRED`: Heuristically deduced.
*   `UNKNOWN`: Unclassified directness.

## 4. Historical Reliability Status
The historical reliability measurement evaluates track records against authoritative ground truth.
*   **Currently Measurable**: Infrastructure is in place to categorize reliability status as `VERIFIED`, `CONTRADICTED`, or `UNVERIFIED`.
*   **Current State**: Because outcome reconciliation (chargebacks, disputes, final settlements) is scheduled for Phase 7+, the `EvidenceReliabilityService` currently returns `UNVERIFIED` with an honest explanatory payload: `"No historical outcome data exists for this evidence observation"`. No synthetic outcomes or fake fraud labels are generated.

## 5. Measurement Snapshots Schema

Quality evaluations are stored as immutable snapshots in `evidence_quality_snapshots`:
*   `internal_id` (`BIGINT`, PK)
*   `evidence_id` (`BIGINT`, FK to `evidence_observations.internal_id`)
*   `evaluation_time` (`TIMESTAMPTZ`, UTC)
*   `freshness_status` (`VARCHAR(32)`)
*   `source_authority` (`VARCHAR(32)`)
*   `source_directness` (`VARCHAR(32)`)
*   `reliability_status` (`VARCHAR(32)`)
*   `methodology_version` (`VARCHAR(32)`)
*   `quality_explanation` (`JSONB` with exact breakdown of age, thresholds, and reasons)
*   `created_at` (`TIMESTAMPTZ`, default now)

Database indexes: `ix_evidence_quality_snapshots_evidence_id`, `ix_evidence_quality_snapshots_evaluation_time`.

## 6. Methodology Versioning
All evaluations tag snapshots with a semantic `methodology_version` (currently `"1.0"`). Any future adjustment to decay thresholds or authority profiles increments this version, ensuring historical evaluations remain explainable and reproducible.

## 7. APIs
*   `GET /api/v1/quality/evidence/{evidence_id}`: Returns the latest quality snapshot for a specific evidence item.
*   `GET /api/v1/quality/payments/{payment_id}`: Returns latest quality snapshots for all evidence items belonging to a payment.

## 8. Frontend Integration
The `PaymentInspector` component displays an **Evidence Quality** section with:
*   Snapshots count and methodology version.
*   Color-coded badges for Freshness (`CURRENT`, `AGING`, `STALE`), Authority (`PRIMARY`, `SECONDARY`), Directness (`DIRECT`, `DERIVED`), and Reliability (`UNVERIFIED`, `VERIFIED`).

## 9. Testing & Test Suite
Unit and integration tests in `backend/tests/test_quality.py`:
*   Freshness threshold transitions (`test_within_current_threshold_is_current`, `test_payment_status_aging_after_4h`, `test_payment_status_stale_after_48h`, `test_payment_amount_not_stale_at_10_days`).
*   Determinism & timezone safety (`test_same_inputs_same_output`, `test_evaluation_time_must_be_timezone_aware`).
*   Temporal re-evaluation simulation across time steps.
*   Source classification for direct vs. derived evidence.
*   Reliability honest reporting (`test_explanation_is_honest`).
*   Methodology version consistency.
*   **Result**: 25/25 quality tests passing; 92/92 total backend tests passing.

## 10. Real Razorpay Verification
*   Executed end-to-end webhook processing with real Razorpay Test Mode webhook (`payment.captured`, Event ID 11).
*   Confirmed automatic trigger of `QualityEngine` generating 6 `EvidenceQualitySnapshot` records.
*   Verified that `PAYMENT_EVENT` is tagged `PRIMARY` / `DIRECT` / `CURRENT` while payload-derived fields are tagged `PRIMARY` / `DERIVED` / `CURRENT`.
*   Verified temporal decay evaluation against real database observations.

## 11. Known Limitations
1.  **Outcome Ground Truth**: Outcome reconciliation (disputes/refunds/chargebacks) is not yet active, so reliability remains `UNVERIFIED` for all current observations.
2.  **API Polling Source**: Live Razorpay API polling is not yet implemented alongside webhooks; all live observations currently come via `RAZORPAY_WEBHOOK`.
3.  **Static Thresholds**: Freshness thresholds are fixed per evidence type rather than dynamic based on merchant velocity.
