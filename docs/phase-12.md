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

**Service:** `app/services/investigation_service.py`
**Router:** `app/api/v1/investigation.py`
**Schemas:** `app/schemas/investigation.py`
**Types:** `app/models/investigation_types.py`

---

## 9. Test Suite

File: `tests/test_investigation.py` — 22 tests:

| Class | Coverage |
|---|---|
| TestGraph | neighbourhood + node types, depth clamping, unique ids, reciprocal-relationship termination, node-limit truncation, `as_of` future exclusion, `node_types` filter, no `raw_payload` in nodes, unknown-payment error |
| TestPath | payment→evidence path, zero-length same-node, missing-node not-found |
| provenance | full EVIDENCE→PAYMENT_EVENT→WEBHOOK_EVENT→PAYMENT chain, missing-evidence error |
| claim support | independent-vs-dependent breakdown |
| dependencies | direct + indirect BFS |
| conflict path | CONFLICT→CLAIM_A/CLAIM_B→EVIDENCE |
| TestSearch | cross-entity results, evidence/claim search, no PII/secrets, limit respected |

---

## 10. Security Properties Verified

- Raw webhook payloads (`raw_payload`) are **always stripped** from graph nodes.
- Customer contact/email PII is **never surfaced** in node metadata.
- All API endpoints return correct HTTP status codes.
- Search results contain only safe derived identifiers.

---

## 11. Implementation status

The engine in `app/services/investigation_service.py` is a **real BFS traversal**
over the persisted relations (not a stub). It builds `pay → order / customer /
event / conflict / snapshot / state-change` at depth 1, `event → evidence /
webhook` and `conflict → claims` at depth 2, and `evidence → source / claim /
related-evidence` at depth 3, with a visited set for cycle safety, `max_nodes` /
`max_edges` bounds reported as `TRAVERSAL_LIMIT_REACHED`, node-id and
edge-tuple de-duplication, `as_of` exclusion of future evidence, and
`node_types` / `relationship_types` filters. Shortest-path is BFS over that
graph's adjacency. Provenance, claim-support, dependency-chain, conflict-path
and cross-table entity search are all implemented against real data.

Verified by `tests/test_investigation.py` (22 tests): traversal, depth clamping,
cycle termination, node-limit truncation, `as_of` filtering, type filtering,
**sensitive-data stripping** (no `raw_payload` / `payload_hash` / PII in any
node), path-finding, provenance chains, claim independence, dependency BFS,
conflict paths, and entity search.

### Known limitations

- Investigation graph is computed on demand (not pre-materialised).
- Path search is scoped to a single payment's graph — paths between nodes in
  different payment graphs are not supported.
- `as_of` filtering applies to evidence `observed_at`; integrity snapshots and
  state changes are not `as_of`-filtered.
