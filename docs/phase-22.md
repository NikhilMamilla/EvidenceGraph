# Phase 22 — AI Claim Understanding & Evidence Matching

## Objective

Add a semantic AI layer above the deterministic EvidenceGraph that can understand merchant defense text, extract structured claims, and identify semantically relevant evidence — while EvidenceGraph remains the sole authority for factual verification.

## Why AI Is Needed

Deterministic rules cannot efficiently parse natural language defense statements. A merchant writes: "The customer received the package on August 18 and signed for it." The system needs to:
1. Understand this contains two claims: CUSTOMER_RECEIVED_GOODS and DELIVERY_DATE
2. Find semantically relevant evidence in the database
3. Pass those links to EvidenceGraph for factual verification

## What AI Does

- Parse natural language defense text
- Extract structured claims with types and confidence
- Identify semantically relevant evidence candidates
- Explain semantic relationships

## What AI Does NOT Do

- Invent evidence
- Override deterministic contradictions
- Override temporal boundaries
- Override provenance checks
- Declare claims verified
- Make financial decisions

## Architecture

```
Merchant Defense Text
        |
        v
+---------------------------+
| AI Claim Understanding    |  ← Semantic parsing
+---------------------------+
        |
        v
Structured Claims
        |
        v
+---------------------------+
| AI Evidence Matching      |  ← Semantic relevance
+---------------------------+
        |
        v
Candidate Evidence Links
        |
        v
+---------------------------+
| EvidenceGraph             |  ← Factual authority
| Deterministic Verification|
+---------------------------+
        |
        v
Final Verification: SUPPORTED / INSUFFICIENT / CONTRADICTED / UNKNOWN
```

## Claim Ontology

For DELIVERY_NOT_RECEIVED disputes:
- DELIVERY_COMPLETED
- CUSTOMER_RECEIVED_GOODS
- DELIVERY_DATE
- DELIVERY_LOCATION
- CUSTOMER_ACKNOWLEDGED_RECEIPT
- SHIPMENT_DISPATCHED
- TRACKING_EVENT_EXISTS

## Deterministic Authority

EvidenceGraph remains authoritative for:
- Evidence identity and deduplication
- Contradiction detection
- Temporal validity
- Coverage analysis
- Source independence
- Provenance validation
- Integrity computation

## Security

- AI provider abstraction (no vendor lock-in)
- Prompt injection protection (untrusted text isolated from system instructions)
- Data minimization (only minimum necessary information sent)
- No secrets in prompts
- No PII beyond necessity
- Input/output hashing for audit

## Failure Handling

- AI failure → EvidenceGraph continues independently
- AI unavailable → system degrades gracefully
- Invalid AI output → rejected, never converted to SUPPORTED
- Timeout → safe fallback

## Limitations

- This is NOT a production fraud/chargeback predictor
- AI performance must be measured against Phase 21 baseline
- Small evaluation set with wide confidence intervals
- No LLM fine-tuning — using prompting only
- Test provider is deterministic — real LLM results will vary
