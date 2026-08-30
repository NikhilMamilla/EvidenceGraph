# Phase 23 — Real LLM Evaluation, Calibration & False-Support Safety

## Objective

Scientifically evaluate whether a real LLM improves the EvidenceGraph defense verification system, with emphasis on safety metrics (false-supported rate, contradiction misses).

## Research Question

Does adding a real LLM semantic layer improve claim extraction and evidence matching compared to:
- Phase 21 deterministic baseline. REF_EVAL_V1: 80% accuracy / 74.7% macro-F1.
  REF_EVAL_V2 (structural value semantics — entity match + conclusive delivery
  status): 90% accuracy / 88.5% macro-F1, zero false-SUPPORTED, 100%
  contradiction recall on the 20-case golden set.
- Phase 22 test-AI provider

## Architecture

```
Merchant Defense Text
        ↓
Real LLM (semantic interpretation)
        ↓
Structured Claims + Evidence Matches
        ↓
EvidenceGraph Deterministic Verification
        ↓
Final Decision (deterministic authority)
```

## Safety Metrics

- **FALSE_SUPPORTED_RATE**: Cases where predicted=SUPPORTED but expected≠SUPPORTED
- **CONTRADICTION_MISS_RATE**: Cases where expected=CONTRADICTED but predicted≠CONTRADICTED
- These are MORE IMPORTANT than overall accuracy

## Three-Way Comparison

| Track | Provider | Purpose |
|-------|----------|---------|
| A | Deterministic EvidenceGraph | Phase 21 baseline |
| B | TestAIProvider | Phase 22 deterministic test |
| C | RealLLMProvider | Phase 23 real evaluation |

## Evaluation Protocol

1. Phase 21 frozen TEST set remains untouched
2. VALIDATION set used for calibration only
3. No prompt tuning against TEST results
4. Real LLM results explicitly marked REAL_LLM
5. Test provider results explicitly marked TEST

## Safety Gate

If false-supported rate exceeds acceptable threshold:
- Pipeline status: SAFETY_GATE_FAILED
- AI NOT marked production-ready

## Limitations

- Small dataset (20 cases) limits statistical significance
- Test provider provides deterministic baseline for comparison
- Real LLM requires configured credentials
- No claims of production accuracy from small samples
