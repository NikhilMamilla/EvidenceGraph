# Phase 5 — Evidence Relationships & Dependency Graph

## 1. Objective
Evidence relationships and dependency graph. Phase 5 builds the foundational relational graph on top of individual Evidence Observation nodes. Its goal is to represent how evidence nodes relate to each other—answering the question "Are these observations from the same source, or are they distinct?" without attempting to assign statistical scores or fraud probability.

## 2. Graph representation
The graph is represented purely in PostgreSQL, avoiding premature infrastructure (like Neo4j). Relationships are directed edges stored in the `evidence_relationships` table connecting records in the `evidence_observations` table.

## 3. Nodes
Evidence observations participate in the graph as the nodes. They are linked via `source_evidence_id` and `target_evidence_id` foreign keys in the relationships table.

## 4. Edges
The actual relationship types implemented are:
* `SAME_EVENT`: Both observations extracted from the exact same business event.
* `SAME_SOURCE`: Both observations originated from the same raw webhook payload.
* `SAME_PAYMENT`: Both observations describe the same canonical payment.
* `SAME_ORDER`: Both observations describe the same canonical order.
* `DERIVED_FROM`: One observation structurally derives from another.
* `DEPENDENT_ON`: One observation logically depends on another.
* `INDEPENDENCE_CANDIDATE`: Observations describe the same subject but originated from *different* webhooks.

## 5. Dependency
Dependency relationships (like `DERIVED_FROM`) explicitly track when one piece of evidence is structurally built upon another. For example, `PAYMENT_STATUS` and `PAYMENT_AMOUNT` are derived from the root `PAYMENT_EVENT` observation. This makes the provenance explicit.

## 6. Independence candidates
`INDEPENDENCE_CANDIDATE` edges are identified by checking if two observations describe the same canonical entity (e.g. `subject_id`) but originated from *different* `webhook_event_id` records. Crucially, observations sharing a `SAME_SOURCE` edge are explicitly blocked from being candidates for independence, ensuring we do not confuse data repetition with independent corroboration.

## 7. Relationship provenance
Every edge records its provenance:
* **Rule**: Recorded as `provenance_metadata` (e.g., `{"reason": "...", "shared_field": "..."}`)
* **Rule version**: Recorded in the `rule_version` column (currently `"1.0"`).
* **Source**: Recorded in `relationship_source` (currently `DETERMINISTIC_RULE`).

## 8. Idempotency
Duplicate edges are prevented using a composite unique constraint on `(source_evidence_id, target_evidence_id, relationship_type)`. The `relationship_engine` uses PostgreSQL's `INSERT ... ON CONFLICT DO NOTHING` to ensure the logic can run multiple times safely without producing duplicate edges.

## 9. APIs
The actual graph endpoints implemented are:
* `GET /api/v1/graph/payments/{payment_id}` — Returns the full evidence graph for a payment (nodes + edges).
* `GET /api/v1/graph/evidence/{evidence_id}/relationships` — Returns all relationship edges for a single evidence observation.

## 10. Frontend
The graph visualization was added to `PaymentInspector.tsx` as an "Evidence Relationships" section at the bottom of the details pane. It displays a grouped list of relationships using specialized badges (e.g., `DERIVED_FROM`, `SAME_SOURCE`, `INDEPENDENCE_CANDIDATE`) to expose the relational structure explicitly and clearly without relying on a complex canvas graph library.

## 11. Testing
The implementation is covered by `tests/test_relationships.py`, which validates the relationship engine logic. It verifies that `SAME_EVENT`, `SAME_SOURCE`, `SAME_PAYMENT`, `DERIVED_FROM`, and `INDEPENDENCE_CANDIDATE` edges are generated correctly, that `INDEPENDENCE_CANDIDATE` correctly ignores same-source pairs, and that no self-loops are generated.

## 12. Real Razorpay verification
The relationship engine was executed against real Razorpay Test Mode data (our existing webhook event ID 11, payment `pay_TSLrT9v7zupeTz`). It successfully generated 92 edges (including `SAME_SOURCE`, `SAME_EVENT`, `SAME_PAYMENT`, and `DERIVED_FROM`) based on the real payloads, proving the system works against genuine provider data.

## 13. Known limitations
* The graph uses relational mapping (PostgreSQL) rather than a native graph database, which means unbounded deep traversals would be slow (though we currently bound queries to a single payment).
* There are no complex temporal or contextual relationship generation rules yet.
* The graph currently only understands Razorpay webhooks as the source of truth, as we haven't integrated the API polling or reconciliation files yet.
