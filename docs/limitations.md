# System Limitations & Boundary Disclosures

EvidenceGraph adheres to strict epistemic honesty. Below is the explicit inventory of system boundaries, operational limitations, and design constraints.

---

## 1. Environment & Benchmark Disclosures
- **Local Benchmark Figures**: All latency and throughput benchmarks documented in local environments (e.g. SQLite unit test suites and single-node Redis/PostgreSQL instances) reflect developer laptop performance and should not be construed as SLA guarantees for distributed multi-region production clusters.
- **Razorpay Test Mode**: Test mode webhooks simulate sandbox gateway operations. While HMAC signatures and event schemas match Razorpay production specifications, payment rails and settlement delays are simulated by Razorpay's sandbox.

---

## 2. Epistemic & Domain Boundaries
- **No Financial / Risk Judgment**: EvidenceGraph analyzes the **trustworthiness, provenance, consistency, coverage, and reliability of evidence**. It explicitly **does NOT** make financial risk decisions, predict chargebacks, approve/deny card transactions, or calculate borrower creditworthiness.
- **Absence of Evidence is Not Evidence of Absence**: When an entity attribute is unobserved (e.g., cardholder name omitted from payload), EvidenceGraph classifies the state as `UNKNOWN` or `MISSING` rather than falsely asserting negative fraud or validation failure.

---

## 3. Cryptographic & Storage Constraints
- **Append-Only Immutability**: Decision traces and raw evidence observations cannot be modified or purged in-place. Purging or GDPR scrubbing requires cryptographic revocation and tombstone logging.
- **SHA-256 Decision Chains**: The hash chain guarantees tamper-evidence for historical decisions within a payment lifecycle. Verification requires access to previous trace hashes.

---

## 4. Operational & Concurrency Boundaries
- **Single-Node Queue Semantics**: The background worker thread currently drains a single Redis list queue. In multi-pod deployments, distributed locking (Redlock) or Kafka partition consumers would be required for horizontal worker scaling.
- **Staleness Latency Window**: When an observation arrives, downstream snapshots (reconciliation, coverage, reliability, integrity) report `STALE` until their respective asynchronous background workers or on-demand trigger endpoints recompute the state.

---

## 5. Defense-Verifier Evaluation Boundaries

- **Golden set size.** The frozen evaluation set is **50 human-constructed
  cases** (`EG-DEFENSE-1.0`), not a sample of real chargeback outcomes. It is
  large enough to exercise every branch of the deterministic evaluator and to
  compute stable per-class metrics, but per-class confidence intervals are still
  wide. Measured accuracy (0.92) and macro-F1 (0.92) are performance **on this
  set**, not a production estimate.

- **Label provenance.** Each case has two label passes by the same author: the
  primary verdict, and an independent second-pass adjudication that re-derives
  the verdict from the evidence list alone. Cohen's κ between them is **0.87**.
  This is **single-annotator + self-adjudication**, not inter-human agreement —
  it measures how stable the four-class taxonomy is under re-derivation, not how
  two independent people would label. A true two-annotator protocol with
  independent recruits is future work.

- **Case construction.** Cases are built from documented evidence templates, not
  extracted from live disputes. Real merchant evidence is messier: partial OCR,
  inconsistent carrier vocabularies, multi-language customer messages. The
  evaluator's value-semantics layer (`_DELIVERY_COMPLETE_PREFIXES` etc.) is a
  curated allow-list, not a learned model, and will mislabel carrier statuses it
  has not seen.

- **Residual errors are directional.** All 4 residual misclassifications on the
  frozen set are `UNKNOWN` → `INSUFFICIENT_EVIDENCE` (a provenance-invalid or
  near-miss entity match read strictly). There are **zero** false `SUPPORTED`
  and **zero** missed contradictions — the two error classes that would actually
  cost a merchant a dispute.

- **Frozen means frozen.** Once `POST /defense/evaluation/freeze` is called (the
  Docker image does this on first boot), the case set, labels and fingerprint
  are immutable; re-seeding is a no-op. Changing the set requires a new dataset
  version, so a reported number can always be tied back to an exact fingerprint.
