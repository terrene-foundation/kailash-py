# Red Team Report R2: Analysis Depth & Cross-SDK Accuracy

**Scope**: Re-examination of analysis accuracy after user flagged superficial kailash-rs research
**Date**: 2026-04-01
**Trigger**: User identified that kailash-rs has moved to native Rust ML primitives, ditched scikit-learn. Previous analysis missed this entirely.

---

## Finding R2-C1: kailash-rs ML Roadmap Missed Entirely (CRITICAL — FIXED)

### What happened
Document 11 (v1) characterized kailash-rs as "inference-only via ONNX/Tract/Candle" and recommended "training stays in Python." The analysis:
- Ran `grep` for keywords instead of reading source code
- Did NOT read `workspaces/kailash-ml-crate/briefs/01-architecture-decisions.md` (8 locked decisions)
- Did NOT read `workspaces/kailash-ml-crate/todos/active/00-index.md` (179 todos)
- Did NOT read the deep analysis document (500KB research corpus)

### What was missed
kailash-rs has a comprehensive, red-team-verified roadmap for native Rust ML:
- 17 crates (kailash-ml-core through kailash-ml-python)
- 455+ sklearn algorithms reimplemented in Rust (no wrappers)
- Gradient boosting engines targeting LightGBM-competitive performance
- faer linear algebra (pure Rust, no BLAS dependency)
- Training primitives: SGD, Adam, L-BFGS, Coordinate Descent, SAGA
- Python bindings via PyO3 (M14)

### Correction
Document 11 rewritten from source code audit (2,866 lines, 12 .rs files + full workspace docs). kailash-rs workspace brief updated to clarify: LLM alignment serving only, NOT all ML training.

### Root cause
Explore agent used `grep` for surface-level keyword matching instead of reading workspace planning documents. **Prevention**: Cross-SDK analysis MUST read workspace briefs, todos, and architecture decisions — not just grep for code.

---

## Finding R2-C2: "Train in Python" Framing Was Partially Wrong (CRITICAL — FIXED)

### What the analysis said
Synthesis document 12, Section 3: "Training stays in Python. Rust handles serving."

### What is correct
- **LLM alignment training** (SFT/DPO/GRPO/KTO): YES, stays in Python (requires PyTorch/TRL)
- **Classical ML training** (regression, trees, clustering, gradient boosting): NO — will be native Rust (kailash-ml v1.0 roadmap)
- **Classical RL training** (SB3/gymnasium): Python only, no Rust equivalent planned

### Correction
Updated synthesis and kailash-rs brief to distinguish LLM alignment (Python) from classical ML (native Rust planned).

---

## Finding R2-H1: kailash-py kailash-ml Wraps Libraries; kailash-rs Implements Natively (HIGH — DOCUMENTED)

### Observation
The two SDKs have fundamentally different ML strategies:
- **kailash-py kailash-ml**: Wraps sklearn, lightgbm, polars — 9 engines as orchestration layers
- **kailash-rs kailash-ml**: Implements from scratch — 17 crates, native Rust algorithms, faer linear algebra

This is valid per EATP D6 (independent implementation, matching semantics) but means:
- Python ML is faster to ship (wrapping existing libraries)
- Rust ML is more ambitious but further from completion (179 todos, implementation pending)
- Feature parity timeline is asymmetric

### Impact
Not a bug — a strategic reality. Both SDKs will have `fit/predict/transform` semantics but different internals.

---

## Finding R2-H2: kailash-align-serving Brief Was Misleading (HIGH — FIXED)

### What it said
"Training happens in Python (kailash-align). This crate handles inference-only deployment."

### Why misleading
This could be read as "ALL ML training happens in Python" — wrong for classical ML, which will be native Rust.

### Correction
Updated brief to explicitly state: "This is specifically for LLM alignment models — classical ML training will be handled natively by kailash-ml."

---

## Finding R2-M1: No Journal Entry for kailash-rs Architecture Decisions (MEDIUM — FIXED)

### What was missing
The 8 architectural decisions (D1-D8) from kailash-rs's `01-architecture-decisions.md` were not referenced in any kailash-py journal entry. This matters because kailash-py's kailash-ml and kailash-align should be aware of kailash-rs's ML strategy.

### Correction
Journal entry 0013-RISK created documenting the analysis failure and correct kailash-rs state.

---

## Finding R2-M2: Synthesis Needs Section on Cross-SDK ML Strategy (MEDIUM — NOTED)

### What's missing
The synthesis (doc 12) has a "kailash-rs Gap" section but doesn't explain the cross-SDK ML strategy:
- Python: wrappers (fast to ship, ecosystem leverage)
- Rust: native implementations (ambitious, performance-focused)
- Alignment: Python-only training, Rust serving
- RL: Python-only for now

### Recommendation
Add a "Cross-SDK ML Strategy" section to the synthesis before /todos.

---

## Convergence Assessment

| Finding | Severity | Status |
|---------|----------|--------|
| R2-C1 | CRITICAL | FIXED — doc 11 rewritten from source audit |
| R2-C2 | CRITICAL | FIXED — synthesis and brief corrected |
| R2-H1 | HIGH | DOCUMENTED — journal 0013 |
| R2-H2 | HIGH | FIXED — kailash-rs brief updated |
| R2-M1 | MEDIUM | FIXED — journal 0013 created |
| R2-M2 | MEDIUM | NOTED — update synthesis before /todos |

**R2 Status**: All critical and high findings resolved. 1 medium item deferred to pre-/todos update.
