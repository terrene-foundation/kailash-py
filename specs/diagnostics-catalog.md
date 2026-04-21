# Diagnostics Catalog

Authoritative index of every concrete adapter that satisfies the cross-SDK `kailash.diagnostics.protocols.Diagnostic` / `JudgeCallable` / `TraceEvent` contracts (issue #567 of kailash-py, cross-SDK parity with kailash-rs#468 / v3.17.1+).

Each entry names the adapter class, its package / import path, the primitives it conforms to, its Tier 2 wiring-test file name (grep-able per `rules/facade-manager-detection.md` §2), the relevant spec file, and the PR that landed it.

## Diagnostic-Protocol Adapters

| Adapter                       | Package / Import                         | Protocols                     | Tier 2 Wiring Test                                                                             | Spec                                                       | PR     |
| ----------------------------- | ---------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | ------ |
| `DLDiagnostics`               | `kailash_ml.diagnostics.DLDiagnostics`   | `Diagnostic`                  | `packages/kailash-ml/tests/integration/diagnostics/test_dl_diagnostics_wiring.py`              | [ml-diagnostics.md](ml-diagnostics.md)                     | #1     |
| `RAGDiagnostics`              | `kailash_ml.diagnostics.RAGDiagnostics`  | `Diagnostic`                  | `packages/kailash-ml/tests/integration/diagnostics/test_rag_diagnostics_wiring.py`             | [ml-diagnostics.md](ml-diagnostics.md)                     | #2     |
| `AlignmentDiagnostics`        | `kailash_align.diagnostics`              | `Diagnostic`                  | `packages/kailash-align/tests/integration/diagnostics/test_alignment_diagnostics_wiring.py`    | [alignment-diagnostics.md](alignment-diagnostics.md)       | #3     |
| `InterpretabilityDiagnostics` | `kaizen.interpretability`                | `Diagnostic`                  | `packages/kailash-kaizen/tests/integration/interpretability/test_interpretability_wiring.py`   | [kaizen-interpretability.md](kaizen-interpretability.md)   | #4     |
| `LLMJudge` / `LLMDiagnostics` | `kaizen.judges`                          | `JudgeCallable`, `Diagnostic` | `packages/kailash-kaizen/tests/integration/judges/test_judges_wiring.py`                       | [kaizen-judges.md](kaizen-judges.md)                       | #5     |
| **`AgentDiagnostics`**        | **`kaizen.observability`**               | **`Diagnostic`**              | **`packages/kailash-kaizen/tests/integration/observability/test_agent_diagnostics_wiring.py`** | **[kaizen-observability.md](kaizen-observability.md)**     | **#6** |
| `GovernanceEngine` extensions | `kailash_pact.governance` (method-level) | native PACT                   | `packages/kailash-pact/tests/integration/governance/test_absorb_capabilities_wiring.py`        | [pact-absorb-capabilities.md](pact-absorb-capabilities.md) | #7     |

## Cross-SDK TraceEvent Producers

| Producer        | Package / Import                       | Shape                                     | Spec                                               |
| --------------- | -------------------------------------- | ----------------------------------------- | -------------------------------------------------- |
| `TraceExporter` | `kaizen.observability.TraceExporter`   | `TraceEvent` → SHA-256 fingerprint → sink | [kaizen-observability.md](kaizen-observability.md) |
| `AuditAnchor`   | `kailash.trust.pact.audit.AuditAnchor` | colon-delimited canonical → SHA-256       | [pact-enforcement.md](pact-enforcement.md)         |
| `AuditChain`    | `kailash.trust.pact.audit.AuditChain`  | linked anchors + genesis sentinel         | [pact-enforcement.md](pact-enforcement.md)         |

All three share the same canonicalization discipline (sort-keys + compact separators + UTF-8 + SHA-256 lowercase hex) but operate on different content envelopes. Forensic correlation across the three streams uses the `"sha256:"` prefix convention from `rules/event-payload-classification.md` §2 — same 8-hex-char contract across Python and Rust.

## Protocol Contracts (Cross-SDK)

| Protocol        | Python Module                                 | Rust Sibling                                       | Schema                        |
| --------------- | --------------------------------------------- | -------------------------------------------------- | ----------------------------- |
| `TraceEvent`    | `kailash.diagnostics.protocols.TraceEvent`    | kailash-rs `trace_event::TraceEvent`               | `schemas/trace-event.v1.json` |
| `JudgeCallable` | `kailash.diagnostics.protocols.JudgeCallable` | kailash-rs equivalent (v3.17.1+)                   | —                             |
| `JudgeInput`    | `kailash.diagnostics.protocols.JudgeInput`    | kailash-rs equivalent                              | —                             |
| `JudgeResult`   | `kailash.diagnostics.protocols.JudgeResult`   | kailash-rs equivalent                              | —                             |
| `Diagnostic`    | `kailash.diagnostics.protocols.Diagnostic`    | N/A (Rust uses trait-dispatch; equivalent concept) | —                             |

## Wiring-Test Naming Contract

Every adapter above has a Tier 2 wiring test whose file name follows `test_<lowercase_adapter_name>_wiring.py`. A missing file is grep-able:

```bash
# DO — grep each adapter's expected wiring test
for adapter in \
  test_agent_diagnostics_wiring.py \
  test_dl_diagnostics_wiring.py \
  test_rag_diagnostics_wiring.py \
  test_alignment_diagnostics_wiring.py \
  test_interpretability_wiring.py \
  test_judges_wiring.py \
  test_absorb_capabilities_wiring.py; do
    find packages -path "*/tests/integration/*" -name "$adapter" | head -1 \
      || echo "MISSING: $adapter"
done
```

Per `rules/orphan-detection.md` §1: every adapter MUST have a production call site within 5 commits of the facade landing; the wiring test proves the call site exists and fires.

## Medical-Metaphor Regression Gate

Per SYNTHESIS-proposal PR#6 gate exit criterion (d), the MLFP donation MUST scrub medical metaphors from every adapter. The gate is a mechanical grep:

```bash
# MUST be empty across every adapter package
rg -i 'stethoscope|x-ray|ecg|flight recorder|langfuse' \
  packages/kailash-ml/src/ \
  packages/kailash-kaizen/src/ \
  packages/kailash-align/src/
```

## Extension Flow

Adding an 8th diagnostic is additive, not architectural:

1. Inherit / satisfy the relevant Protocol (`Diagnostic`, `JudgeCallable`).
2. Pick the owning package per `rules/framework-first.md` domain binding.
3. Ship the adapter with a Tier 2 wiring test named `test_<name>_wiring.py`.
4. Add a row to this catalog + a spec file under `specs/`.
5. Run the medical-metaphor regression grep.

No new framework. No architectural review. The cross-SDK contract at `src/kailash/diagnostics/protocols.py` is the single source of truth; everything else is a concrete adapter.
