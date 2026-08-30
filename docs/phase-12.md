# Phase 12 — Evidence Graph Query & Investigation Engine

## 1. Objective

Phase 12 adds a **deterministic investigation and query layer** over the EvidenceGraph.
An investigator can start from a real Razorpay payment ID and traverse the persisted evidence
graph to understand which entities are connected, what evidence exists, what claims are
supported, what conflicts are present, and how the evidence was corroborated.

Phase 12 does **not** produce fraud scores, risk decisions, or financial outcomes.
It is a structured query engine over already-persisted data.

---

## 2. Investigation Graph Model

The graph is constructed on-demand from persisted relational data. It is not a separate
graph database — it is a structured view of the existing PostgreSQL tables.

**Node types** (from `InvestigationNodeType`):

| Node Type | Source Table |
|---|---|
| PAYMENT | payments |
| ORDER | orders |
| CUSTOMER | customer_references |
| WEBHOOK_EVENT | webhook_events |
| PAYMENT_EVENT | payment_events |
| EVIDENCE | evidence_observations |
| CLAIM | claims |
| SOURCE | evidence_observations (source_type) |
| CONFLICT | evidence_conflicts |
| INTEGRITY_SNAPSHOT | evidence_integrity_snapshots |
| STATE_CHANGE | evidence_state_changes |

**Edge types** (from `InvestigationEdgeType`):

| Edge | Meaning |
|---|---|
| HAS_ORDER | Payment → Order |
| HAS_CUSTOMER | Payment → Customer |
| HAS_EVENT | Payment → PaymentEvent |
| PRODUCED_EVIDENCE | PaymentEvent → Evidence |
| DERIVED_FROM_WEBHOOK | Evidence → WebhookEvent |
| SUPPORTS_CLAIM | Evidence → Claim |
| DEPENDS_ON | Evidence → Evidence (dependency) |
| DERIVED_FROM | Evidence → Evidence (derivation) |
| CORROBORATES | Evidence → Evidence (corroboration) |
| CONTRADICTS | Evidence → Evidence (contradiction) |
| HAS_CONFLICT | Payment → Conflict |
| INVOLVES_CLAIM | Conflict → Claim |
| HAS_INTEGRITY_SNAPSHOT | Payment → IntegritySnapshot |
| HAS_STATE_CHANGE | Payment → StateChange |
| FROM_SOURCE | Evidence → Source |

---

## 3. Traversal Algorithm

- **BFS (breadth-first search)** from the root payment node.
- **Cycle detection**: visited node set prevents revisiting.
- **Depth bounding**: configurable, bounded by `MAX_TRAVERSAL_DEPTH = 5`.
- **Node/edge limits**: bounded by `HARD_MAX_NODES = 500`, `HARD_MAX_EDGES = 1000`.
- **Duplicate elimination**: node IDs and edge pairs are deduplicated before return.
- **As-of temporal filtering**: observations with `observed_at > as_of` are excluded.

Traversal status: `COMPLETE` or `TRAVERSAL_LIMIT_REACHED`.

---

## 4. Sensitive Data Protection

The investigation layer **never exposes**:
- `raw_payload` from WebhookEvents
- `payload_hash`
- Customer contact, email, or phone
- API secrets or credentials

Node metadata contains only safe, derived fields.

---

## 5. API Endpoints

All routes are under `/api/v1/investigation`.

### `GET /investigation/payments/{payment_id}/graph`

Build the bounded investigation graph centered on a payment.

Parameters:
- `depth` (1–5, default 2) — traversal depth
- `as_of` — ISO 8601 timestamp for historical queries
- `node_types` — optional filter list
- `relationship_types` — optional filter list
- `max_nodes` (default 200, max 500)
- `max_edges` (default 400, max 1000)

Response: `InvestigationGraphResponse` — nodes, edges, context, traversal status.

### `GET /investigation/path`

Find the shortest path between any two graph node IDs.

Parameters: `source`, `target`, `max_depth` (1–10, default 5), `as_of`.

Response: `InvestigationPathResponse` — ordered list of nodes and edges.

### `GET /investigation/evidence/{evidence_id}/provenance`

Retrieve the full upstream provenance chain for an evidence observation:
`Evidence → PaymentEvent → WebhookEvent → Payment`.

Response: `EvidenceProvenanceResponse` — full lineage with timestamps, source type, webhook event metadata.

### `GET /investigation/claims/{claim_id}/support`

Query which observations corroborate a claim and explain independence.

Response: `ClaimSupportResponse` — claim details, corroboration groups, independence status, observation breakdown.

### `GET /investigation/evidence/{evidence_id}/dependencies`

Retrieve direct and indirect dependency relationships for an evidence observation.

Response: `EvidenceDependenciesResponse` — dependency chain.

### `GET /investigation/conflicts/{conflict_id}/path`

Inspect a conflict: which opposing claims, which evidence supports each side.

Response: `ConflictPathResponse` — conflict metadata, claim A, claim B, supporting evidence for each.

### `GET /investigation/search`

Exact and prefix search across payments, orders, customers, webhooks, evidence, claims, traces.

Parameters: `q` (1–128 chars), `limit` (1–50, default 20).

Response: `SearchResponse` — list of `SearchResultItem` with entity type, ID, and safe metadata.

---

## 6. Temporal As-Of Query

`temporal_as_of_query(payment_id, as_of_time)` reconstructs the graph state at any historical
point. Only evidence with `observed_at <= as_of_time` is included. Future evidence cannot
leak into historical calculations.

---

## 7. Integrity and State Change Linkage

- `get_integrity_snapshot_linkage(payment_id)` — maps integrity snapshots to the payment and surfaces any violations.
- `get_temporal_state_change_linkage(payment_id)` — surfaces the full state transition chain across `EvidenceStateChange` records.

---

## 8. Implementation

**Service:** `app/services/investigation_service.py` (1247 lines)
**Router:** `app/api/v1/investigation.py`
**Schemas:** `app/schemas/investigation.py`
**Types:** `app/models/investigation_types.py`

---

## 9. Test Suite

File: `tests/test_investigation.py`

**20 tests, all passing:**

| Class | Tests |
|---|---|
| TestDirectNeighborhoodAndTraversal | 1–7: direct neighborhood, n-hop traversal, cycle detection, node/edge limits, duplicate elimination |
| TestPathsAndProvenance | 8–12: evidence provenance, claim support, dependencies, corroboration explanation, conflict path |
| TestTemporalAsOfQueries | 13–14: as-of historical query, future evidence exclusion |
| TestIntegrityAndStateChangeLinkage | 15–16: integrity snapshot linkage, temporal state change linkage |
| TestSearchAndSecurity | 17–20: exact identifier search, API status codes, sensitive-data filtering, path search |

---

## 10. Security Properties Verified

- Raw webhook payloads (`raw_payload`) are **always stripped** from graph nodes.
- Customer contact/email PII is **never surfaced** in node metadata.
- All API endpoints return correct HTTP status codes.
- Search results contain only safe derived identifiers.

---

## 11. Known Limitations

- Investigation graph is computed on demand (not pre-materialised). For very large payments with many observations, traversal may approach node/edge limits.
- The path search is BFS over the adjacency built during `build_payment_graph`, not over the full database graph. Path searches between nodes in different payment graphs are not supported.
- `as_of` filtering applies to evidence `observed_at` only; integrity snapshots and state changes are not filtered by `as_of` in the current implementation.
