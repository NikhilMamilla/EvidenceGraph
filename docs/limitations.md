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
