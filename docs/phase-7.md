# Phase 7: Evidence Independence, Concentration & Corroboration Engine

## 1. Objective
Phase 7 introduces the structural measurement engine for EvidenceGraph. It solves the fundamental problem in evidence analysis: **distinguishing multiple distinct observations from multiple independent signals**.
Phase 7 measures evidence concentration, canonical claims, evidence grouping, and corroboration structure without computing a composite "Evidence Integrity Score" or making subjective trust/risk judgments.

## 2. Why Evidence Counting is Insufficient
A naive risk system might assume that having 6 pieces of evidence (`status=paid`, `amount=10000`, `currency=INR`, `method=netbanking`, `event=order.paid`, `order_id=order_...`) represents 6 independent signals.
In reality:
*   All 6 observations originated from a single provider webhook event (`order.paid`).
*   They share the same source (`RAZORPAY_WEBHOOK`), the same provider timestamp, and the same derivation chain.
*   Counting raw rows as independent validation creates a false illusion of multi-factor certainty.
Phase 7 quantifies the true concentration and corroboration structure of evidence.

## 3. Canonical Claims Model
A **Claim** represents an observable abstract proposition about an entity (e.g. `PAYMENT_STATUS = paid`, `PAYMENT_AMOUNT = 10000 INR`), distinct from the immutable **EvidenceObservation** instances that support it:
$$\text{Claim} \leftarrow \text{EvidenceClaimLink} \rightarrow \text{EvidenceObservation}$$

### Implemented Claim Types
*   `PAYMENT_STATUS`: Proposition about payment/order status (`paid`, `captured`, `failed`).
*   `PAYMENT_AMOUNT`: Proposition about monetary value (`10000`).
*   `PAYMENT_CURRENCY`: Proposition about ISO currency (`INR`).
*   `PAYMENT_METHOD`: Proposition about payment method (`upi`, `netbanking`, `card`).
*   `ORDER_ASSOCIATION`: Proposition linking a payment to an order ID.
*   `CUSTOMER_IDENTIFIER`: Proposition about customer references.
*   `PAYMENT_EVENT_OCCURRENCE`: Proposition recording the occurrence of a lifecycle event.

Observations with equivalent propositions resolve to the same canonical `Claim` row, linking multiple observations to one claim.

## 4. Evidence Groups
An `EvidenceGroup` clusters observations sharing an underlying structural origin or delivery context.
Grouping **does not mutate or merge** underlying evidence observations.

### Implemented Group Types
1.  `SAME_PAYMENT_EVENT`: All observations produced by the same payment lifecycle event (`payment_event_id`).
2.  `SAME_WEBHOOK_EVENT`: All observations delivered in the exact same HTTP webhook transmission (`webhook_event_id`).
3.  `SAME_SOURCE`: All observations originating from the same system source mechanism (`RAZORPAY_WEBHOOK`, `RAZORPAY_API`).

## 5. Dependency Integration
Phase 7 leverages the deterministic relationship graph from Phase 5 (`SAME_EVENT`, `SAME_SOURCE`, `SAME_PAYMENT`, `DERIVED_FROM`, `INDEPENDENCE_CANDIDATE`) to trace whether observations are linked in common derivation paths or represent separate events.

## 6. Independence Candidates
The engine uses cautious classification for independence:
*   `INDEPENDENT_CANDIDATE`: Multiple observations supporting the same claim originated from genuinely different source mechanisms (e.g., webhook delivery + synchronous REST API verification).
*   `DEPENDENT`: Multiple observations supporting the same claim across distinct temporal events from the same source.
*   `SAME_SOURCE`: Multiple observations extracted from the exact same event or payload.
*   `UNKNOWN`: Single observation (insufficient structural data to assess independence).

The system **never** declares unconditional statistical independence; it only flags structural candidates.

## 7. Corroboration Engine
`CorroborationService` inspects the set of observations supporting each canonical claim and classifies the corroboration:
*   `SINGLE_OBSERVATION`: Claim has exactly 1 supporting observation.
*   `SAME_SOURCE_CORROBORATION`: Multiple observations from the same source mechanism support the claim.
*   `TEMPORAL_CORROBORATION`: Observations at distinct timestamps or across different provider events support the claim.
*   `MULTI_SOURCE_CORROBORATION`: Observations from different source types support the claim.

## 8. Concentration & Structural Metrics
Phase 7 calculates raw structural quantities and an established mathematical concentration metric:
*   `total_observations`: Total evidence items linked to the payment entity.
*   `distinct_claims`: Number of unique canonical propositions supported.
*   `distinct_sources`: Number of distinct provider ingestion mechanisms.
*   `distinct_events`: Number of distinct provider lifecycle events.
*   `distinct_groups`: Total evidence groups formed.
*   `largest_group_size`: Count of observations in the largest payment event group.
*   `corroborated_claim_count`: Claims supported by $>1$ observation.
*   `multi_source_claim_count`: Claims supported by $>1$ distinct source type.

### Group Herfindahl-Hirschman Index (HHI)
$$\text{HHI} = \sum_{i=1}^k \left(\frac{n_i}{N}\right)^2$$
Where $n_i$ is the number of observations belonging to provider event $i$, and $N$ is total observations:
*   $HHI = 1.00$: Total concentration (all observations come from a single event).
*   $HHI < 1.00$: Dispersed observations across multiple provider events.

## 9. Methodology Versioning
All structural evaluations and snapshots are stamped with `methodology_version = "1.0"`.

## 10. APIs
*   `GET /api/v1/payments/{payment_id}/structure`: Returns the full structural snapshot, claims, evidence groups, and corroborations.
*   `GET /api/v1/payments/{payment_id}/claims`: Returns canonical claims and observation counts for a payment.
*   `GET /api/v1/claims/{claim_id}/evidence`: Returns all individual evidence observations linked to a specific claim.

## 11. Frontend Integration
The `PaymentInspector` component in `frontend/src/components/PaymentInspector.tsx` renders:
*   **Structural Concentration Metrics Grid**: Observations count, distinct claims, provider events, largest group, and the Group HHI index.
*   **Canonical Claims & Corroboration**: Detailed propositions with observation counts, corroboration badges, and independence candidate statuses.
*   **Evidence Origin Groups**: Breakdowns of observations clustered by event and source.

## 12. Testing & Test Suite
Unit and integration tests in `backend/tests/test_structure.py`:
*   `TestClaims`: Mapping logic, canonical claim deduplication, link creation, absence of values.
*   `TestGrouping`: Event grouping, webhook grouping, source grouping, immutability of evidence.
*   `TestCorroboration`: Single observation, same source, temporal corroboration, multi-source corroboration.
*   `TestConcentrationAndHHI`: HHI = 1.0 for single event, HHI = 0.68 for split events (8/2 split), largest group size.
*   `TestDeterminismAndVersioning`: Deterministic evaluation and version tagging.
*   `TestStructureAPI`: Endpoints for structure, claims, and claim evidence lookup.
*   **Result**: 14/14 structure tests passing; 106/106 total backend tests passing.

## 13. Real Razorpay Test Mode Verification
Verified against real Razorpay Test Mode payment `pay_TSLrT9v7zupeTz` (Event 11: `order.paid`):
*   **Real Razorpay event**: YES (`order.paid`, 6 observations)
*   **Claims generated**: YES (6 canonical claims mapped)
*   **Evidence groups**: YES (3 groups: `payment_event_1`, `webhook_event_11`, `source_RAZORPAY_WEBHOOK`)
*   **Corroboration**: YES (`SINGLE_OBSERVATION` for each claim)
*   **Independence candidates**: YES (`UNKNOWN` cautiously assigned)
*   **Concentration metric**: YES (HHI = 1.00, largest group = 6 observations)
*   **Structure API**: YES (Returns 200 OK with full snapshot)
*   **Frontend**: YES (Renders metrics, claims, corroborations, and groups)

## 14. Known Limitations
1.  **Single Ingestion Source**: Currently only `RAZORPAY_WEBHOOK` is active in the live pipeline. Multi-source corroboration (`MULTI_SOURCE_CORROBORATION`) has been unit-tested and modelled, but live verification of multi-source corroboration awaits active REST API polling in a future phase.
2.  **Outcome Tracking**: Claims record observable propositions (e.g. status), not future business outcomes (e.g. chargeback dispute resolution).
