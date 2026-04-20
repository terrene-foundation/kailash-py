# Issue #567 — Cross-SDK Parity Decision (kailash-rs)

**Governing rule**: `rules/cross-sdk-inspection.md` MUST Rule 1 + MUST Rule 3 (EATP D6: independent implementation, matching semantics).

Per-helper parity verdict: which of the seven MLFP helpers warrant a sibling `esperie/kailash-rs` issue (with `cross-sdk` label) and which are py-only by design.

---

## Decision Matrix

| Helper                                                       | Rust parity         | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                    | Sibling ticket action                                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------ | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **DLDiagnostics**                                            | **No**              | Py-only. Tightly coupled to PyTorch internals (`register_forward_hook`, autograd intermediate tensors). `kailash-ml-rs` has no torch binding and the equivalent Rust ecosystem (burn, candle, tch-rs) diverges per-framework. Rust side is more naturally served by backend-native probes.                                                                                                                                   | File tracking issue `kailash-rs#NNN` noting the decision + `not-applicable-py-only` label. No implementation work.                                                                                                                                                                           |
| **LLMDiagnostics + JudgeCallable**                           | **Yes — MANDATORY** | LLM-as-judge is a language-agnostic pattern. kailash-rs has `kailash-kaizen-rs` with Delegate-equivalent (`Agent::delegate`) and cost tracking (`kailash-kaizen-rs::cost`). Scoring semantics (position-swap, self-consistency, refusal calibration) are model-call orchestration, not language-specific.                                                                                                                    | File `kailash-rs#NNN` with `cross-sdk` label. Scope: `kailash_kaizen::judges::{LLMJudge, FaithfulnessJudge, ...}` module with matching signatures. Semantic contract (e.g., JudgmentRecord fields) MUST match byte-for-byte so a py-emitted judgment record deserialises in a Rust consumer. |
| **InterpretabilityDiagnostics**                              | **Deferred**        | Technically portable (attention heatmaps, logit lens, linear probes are tensor ops), but the HF transformers dependency is the heavy lift; Rust equivalents via `candle-transformers` exist but are partial. Not a parity-now obligation.                                                                                                                                                                                    | File `kailash-rs#NNN` as `cross-sdk` + `deferred` + `feature-request`. No implementation commitment this cycle.                                                                                                                                                                              |
| **RAGDiagnostics**                                           | **Yes — MANDATORY** | recall@k / precision@k / MRR / nDCG are pure math primitives that should produce byte-identical values across SDKs for the same ranked-list input. This is exactly the EATP D6 parity surface — a polyglot system with py-side ingestion and rs-side retrieval needs identical metrics.                                                                                                                                      | File `kailash-rs#NNN` with `cross-sdk` label. Scope: `kailash_ml_rs::metrics::rag::*` — pure function API, no async, deterministic. Cross-SDK regression test: same (relevance, retrieved) input vector → same metric values (IEEE-754 exact up to sum order).                               |
| **AgentDiagnostics + TraceEvent**                            | **Yes — MANDATORY** | Agent-trace capture is the same shape in both SDKs. kailash-rs already has `kailash-kaizen-rs::observability` (tracing, metrics, audit — via the `opentelemetry` crate). `TraceEvent` semantics MUST match cross-SDK so traces from a py agent and a rs agent are comparable in the same dashboard (this is the original EATP D6 use case).                                                                                  | File `kailash-rs#NNN` with `cross-sdk` label. Requires: (a) same JSON schema for TraceEvent, (b) same cost field (microdollars via `CostTracker` equivalent), (c) same correlation-ID propagation (`run_id`). BP-label: `BP-NNN cross-sdk-trace-parity`.                                     |
| **AlignmentDiagnostics**                                     | **No**              | `kailash-align` exists as py-only; no `kailash-align-rs` package. LoRA/DPO training in Rust is not currently on the roadmap. Diagnostic parity has no consumer.                                                                                                                                                                                                                                                              | No ticket required. Document in #567 closure: "no Rust Align SDK target".                                                                                                                                                                                                                    |
| **GovernanceDiagnostics** (redesign → PACT engine extension) | **Yes — MANDATORY** | PACT is EATP's governance backbone and already has `kailash-pact-rs` with the same D/T/R grammar. Any audit-chain verification / budget-snapshot / envelope-snapshot method added to the py `GovernanceEngine` MUST have a Rust mirror — otherwise cross-SDK governance reads diverge. `rules/cross-sdk-inspection.md` MUST Rule 3a applies (structural API-divergence disposition): signature invariant test on BOTH sides. | File `kailash-rs#NNN` with `cross-sdk` label once the py PACT-engine extension PR opens. Semantic parity: `GovernanceEngine::verify_audit_chain`, `GovernanceEngine::snapshot_envelopes`. Chain-hash algorithm (SHA-256 prev_hash) MUST match byte-for-byte (already specified by PACT).     |

---

## Parity Summary

- **Mandatory Rust parity (4)**: LLMDiagnostics, RAGDiagnostics, AgentDiagnostics, GovernanceDiagnostics-as-engine-methods.
- **Py-only (2)**: DLDiagnostics, AlignmentDiagnostics.
- **Deferred (1)**: InterpretabilityDiagnostics.

---

## Cross-SDK Contract Requirements

For every Mandatory item above, per `rules/cross-sdk-inspection.md` MUST Rule 3a:

1. **Shared serialisation contract** (JSON schema or serde-compatible struct) — a trace/judgment/metric record emitted by one SDK MUST round-trip through the other.
2. **Binary-identical hash values** where cryptographic chain is involved (PACT audit chain SHA-256; any future HMAC-signed envelope).
3. **Signature invariant tests on both sides** — if the py `LLMJudge.evaluate()` takes `(prompt, response_a, response_b, *, tenant_id=None)`, the Rust `LLMJudge::evaluate(prompt, response_a, response_b, tenant_id)` MUST match. A structural test locks the signature so a future refactor of one SDK toward a divergent shape fails loudly.
4. **Microdollar cost arithmetic** — integers only across both SDKs; no float addition. Cross-SDK regression test asserts py `CostTracker` and rs `CostTracker` agree on the same usage record to the byte.

---

## Sibling-Issue Template

```markdown
# Cross-SDK parity: <Helper> (mirror of terrene-foundation/kailash-py#567)

**Cross-SDK alignment**: this is the Rust equivalent of
https://github.com/terrene-foundation/kailash-py/issues/567.

Py-side delivery: kailash-<package> X.Y.Z
Rust-side scope: kailash-<package>-rs X.Y.Z

**Contract** (MUST match py):

- <struct/trait signatures>
- <serde schema>
- <cost arithmetic: microdollars, no float>
- <hash/signature invariants>

**Tests**:

- Tier 2 through the framework facade (not direct module import)
- Cross-SDK regression test: py emits record → rs deserialises → rs emits equivalent → py deserialises

Label: `cross-sdk`
```

---

## Closure Checklist (to be completed when filing)

- [ ] File 4 mandatory + 1 deferred + 2 py-only decisions as comments on `terrene-foundation/kailash-py#567`.
- [ ] File 4 `cross-sdk`-labelled issues in `esperie/kailash-rs` (one per mandatory item).
- [ ] Cross-reference every ticket pair (py issue ↔ rs issue) per MUST Rule 2.
- [ ] Add EATP D6 cross-SDK regression tests for each mandatory item at release time (py and rs land independently but test parity).
