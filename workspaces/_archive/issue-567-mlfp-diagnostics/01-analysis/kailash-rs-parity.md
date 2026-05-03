# kailash-rs Cross-SDK Parity Analysis — MLFP Diagnostics (kailash-py#567)

## Executive Summary

The Terrene Foundation MLFP course offers 7 diagnostics helpers (~7,300 LOC).
Of those, **3 are viable for kailash-rs parity** (RAG, Agent, Governance),
and **4 are py-only** (DL, LLM, Interpretability, Alignment) because the
required runtimes (Rust autodiff, HF transformers, judge engine, alignment)
do not exist in kailash-rs today. Recommendation: ship all three parity BPs
(BP-051 / BP-052 / BP-053) in sequence, with BP-053 (Governance) first since
it reuses the existing SHA-256 + prev_hash chain already implemented in
`kailash-core::audit_log::AuditEntry` and `kailash-enterprise::audit::sqlite`.

- Complexity: Moderate (3 new crates / sub-modules; 1 fingerprint contract)
- Next BP number: **BP-051** (last observed: BP-050 in
  `workspaces/use-feedback-triage/04-validate/BP-050-express-mutation-redaction.md`)

---

## 1. Rust Surface Inventory

### 1.1 RAGDiagnostics

- **Existing host crate**: **none** — `kailash-kaizen` has no `rag` /
  `retriever` module. `kailash-kaizen/src/lib.rs` exposes:
  `a2a, agent, checkpoint, cost, error, llm, manifest, mcp, memory,
observability, output, response_schema, topo_sort, types, trust,
governance, ontology, l3`. Zero RAG surface. Grep for
  `rag|Retriever|RetrievalMetric|recall|ndcg|mrr|bm25` across
  `crates/kailash-kaizen/src` returned zero matches in implementation
  files (only LLM deployment mocks and docs).
- **Recommended placement**: **new crate `crates/kailash-rag-diagnostics`**
  — RAG primitives do NOT exist in kailash-kaizen today, so the
  diagnostics crate CANNOT sit "next to" a retriever abstraction. A fresh
  crate keeps the kaizen dep-graph clean (kaizen already has 18 optional
  features and a dense Cargo.toml; adding `rag-diagnostics` as a gated
  module inside kaizen would pull polars-rs into the kaizen dep tree for
  users who only want agents). Public symbols it would own:
  `RetrievalMetrics`, `Recall`, `Precision`, `MRR`, `NDCG`,
  `ContextUtilization`, `RetrieverLeaderboard`. Zero naming collisions
  verified against `crates/*/src/lib.rs`.
- **What exists today**: nothing reusable. The metric math (recall@k,
  precision@k, MRR, nDCG) is pure Rust and does not need a runtime dep.
- **What must be built**: full crate from scratch (~700 LOC parity with
  Python's RAGDiagnostics 705 LOC).

### 1.2 AgentDiagnostics + TraceEvent

- **Existing host crate**: `kailash-kaizen::observability` — already has
  `MetricsCollector`, `TracingManager`, `Span`, `Trace`, `SpanContext`,
  `LogAggregator`, `ObservabilityManager`. The Rust-side TraceEvent
  equivalent is `Span` / `Trace` in
  `crates/kailash-kaizen/src/observability/tracing.rs` (NOT a `TraceEvent`
  struct by that name). Grep for `TraceEvent|trace_event` returned zero
  matches — no naming collision with Python's `TraceEvent`.
- **Recommended placement**:
  `crates/kailash-kaizen/src/observability/diagnostics.rs` (new module
  under existing `observability/`). New public symbols: `AgentDiagnostics`,
  `TraceEvent` (dataclass-equivalent struct), `ToolUsageReport`,
  `LoopDetectionReport`, `CostBreakdown`, `Timeline`.
- **What exists today**: `Span` (parent/child hierarchy),
  `MetricsCollector` (tool-call counters, token counts, latency),
  `LogAggregator` (ring buffer). These are reusable PRIMITIVES — the
  diagnostics layer sits ABOVE them as a "compute reports from captured
  spans" consumer. The `TraceEvent` struct Python ships (a single captured
  event with tool_name, inputs, outputs, duration, cost, error) maps
  cleanly onto a serialized `Span` + metadata.
- **What must be built**: `AgentDiagnostics` capture+analysis API
  (~700 LOC parity with Python 668+360 = 1028 LOC; Rust idioms should
  shrink to ~700 due to no GIL and native dataclass ergonomics with
  serde).

### 1.3 GovernanceDiagnostics

- **Existing host crate**: `kailash-pact::audit` — already has
  `TieredAuditEvent`, `TieredAuditStore`, `TieredAuditRouter`,
  `DurabilityTier`, `MemoryAuditStore`, `FileAuditStore`,
  `SqliteAuditStore`. Additional audit surface lives in:
  - `kailash-enterprise::audit::sqlite` (SHA-256 + `prev_hash` Merkle chain
    with SQLite append-only triggers)
  - `kailash-core::audit_log::AuditLog` (SHA-256 + `prev_hash` sequence
    numbers, `verify_chain()` method)
  - `eatp::ledger` (SHA-256 with `prev_hash` prepended to content)
- **Recommended placement**:
  `crates/kailash-pact/src/diagnostics.rs` (new module at crate root).
  New public symbols: `GovernanceDiagnostics`, `ChainInspector`,
  `BudgetConsumptionReport`, `NegativeDrillSuite`, `EnvelopeSnapshot`.
  Zero naming collisions verified against
  `crates/kailash-pact/src/lib.rs` (current pub mods: `agent, audit,
observation, recorder, stores, mcp, yaml`).
- **What exists today**: ALL primitives needed. `AuditLog::verify_chain()`
  (`kailash-core/src/audit_log.rs:36`) already recomputes SHA-256 hashes
  and validates linkage. `AppendOnlyAuditStore` in
  `kailash-enterprise::audit::sqlite` already re-verifies the Merkle
  chain. The diagnostics layer is PURELY a read-only inspector on top.
- **What must be built**: `GovernanceDiagnostics` read-only inspector
  (~600 LOC parity with Python 716 LOC).

---

## 2. BP Proposal Drafts

### BP-051 — Governance Diagnostics Parity (kailash-pact)

- **Scope**: Read-only governance audit inspector mirroring kailash-py's
  `GovernanceDiagnostics`. Exposes chain integrity verification (reuses
  `AuditLog::verify_chain` from kailash-core), budget consumption rollup,
  negative-drill suite (test-vector runner), envelope snapshot export.
- **Est LOC**: ~600 (Rust idioms over Python 716 LOC).
- **Crate**: `crates/kailash-pact` (new module `diagnostics.rs`).
- **Python parity**: `packages/kailash-kaizen/src/kaizen/governance/diagnostics.py`
  and kailash-py issue #567.
- **Priority**: FIRST of the three — all primitives exist; pure aggregation layer.

### BP-052 — Agent Diagnostics Parity (kailash-kaizen observability)

- **Scope**: Rust-side `AgentDiagnostics` + `TraceEvent` built atop the
  existing `observability::{Span, Trace, MetricsCollector}`. Adds tool
  usage rollup, loop detection (repeated tool-call pattern analysis),
  cost breakdown, timeline export.
- **Est LOC**: ~700.
- **Crate**: `crates/kailash-kaizen` (new module
  `observability/diagnostics.rs`).
- **Python parity**: Python `AgentDiagnostics` (668 LOC) +
  `TraceEvent` (360 LOC) per kailash-py issue #567.

### BP-053 — RAG Diagnostics Parity (new crate)

- **Scope**: New crate `kailash-rag-diagnostics` providing
  `RetrievalMetrics` (recall@k, precision@k, MRR, nDCG), context
  utilisation, retriever leaderboard. Pure compute; no retriever runtime
  dep. Backend abstraction is the caller-supplied
  `Vec<(query, retrieved_docs, relevant_docs)>` tuples.
- **Est LOC**: ~700.
- **Crate**: **new** `crates/kailash-rag-diagnostics` (does NOT exist
  today; explicit new crate to avoid bloating kailash-kaizen with polars
  and dataframe deps).
- **Python parity**: Python `RAGDiagnostics` (705 LOC) per kailash-py
  issue #567.

---

## 3. Rust Crate Placement Summary

| Helper                | Host                                   | New module / crate               |
| --------------------- | -------------------------------------- | -------------------------------- |
| RAGDiagnostics        | NEW CRATE                              | `crates/kailash-rag-diagnostics` |
| AgentDiagnostics      | `crates/kailash-kaizen::observability` | `observability/diagnostics.rs`   |
| GovernanceDiagnostics | `crates/kailash-pact`                  | `diagnostics.rs`                 |

Rationale for `kailash-rag-diagnostics` being a NEW crate (not a
kaizen sub-module): kaizen has 18 optional features and a Cargo.toml that
already tips 180 lines; adding polars-rs + dataframe primitives for a
diagnostics consumer that does not share runtime with the LLM/tool code
would force every kaizen user to absorb the dep weight. A separate crate
lets users pull diagnostics into test/CI workflows without affecting
production agent builds.

---

## 4. Dependency Analysis

| Crate                                    | Existing? | Deps introduced                                                    |
| ---------------------------------------- | --------- | ------------------------------------------------------------------ |
| `crates/kailash-rag-diagnostics` (new)   | NO        | `serde`, `serde_json`, `thiserror`, **polars** (dataframe export), |
|                                          |           | `plotters` (leaderboard plot, optional feature)                    |
| `crates/kailash-kaizen::observability::` | YES       | NONE — all deps already in kailash-kaizen (`serde`, `dashmap`,     |
| `diagnostics.rs`                         |           | `chrono`, `indexmap`, `tracing`)                                   |
| `crates/kailash-pact::diagnostics`       | YES       | NONE — `sha2` + `hex` already pulled via `kailash-pact::audit`     |
|                                          |           | (`TieredAuditEvent::content_hash`), `chrono` already in workspace  |

**Flag**: `polars-rs` is **not currently in the kailash-rs workspace**.
Check `Cargo.lock` before BP-053; if not present, the BP owner must
evaluate whether polars is worth the binary-size cost (~30 MB compiled
debug) versus writing the dataframe layer in pure Rust with `serde_json`
output (recommended for parity diagnostics — dataframe export is a
convenience, not a hard requirement). `plotters-rs` should be gated
behind a `plots` feature flag so the default build stays slim.

Per `rules/dependencies.md`: no caps on deps we don't directly import;
use latest stable (`polars = ">=0.40"` if included; `plotters = ">=0.3"`
if included). Per `dependencies.md` Rule "Declared = Imported", every
new `use polars::` MUST land with a same-commit Cargo.toml entry.

---

## 5. Cross-SDK Fingerprint Contract — Critical Finding

**kailash-py `GovernanceDiagnostics` SHA-256 chain format**:

- `prev_hash`: hex-encoded SHA-256 of preceding entry (empty string for genesis,
  `"0"*64` in kailash-py's `trust/audit_store.py::_GENESIS_HASH`)
- `hash`: SHA-256 over canonical serialized content including `prev_hash`

**kailash-rs existing implementations**:

| Path                                     | Genesis sentinel | Hash input                                                                          | Drift? |
| ---------------------------------------- | ---------------- | ----------------------------------------------------------------------------------- | ------ |
| `kailash-core/src/audit_log.rs`          | `""` empty       | `"{seq}:{prev_hash}:{ts}:{evt}:{actor}:{action}:{res}:{out}:{md}"` formatted string | YES    |
| `kailash-enterprise/src/audit/sqlite.rs` | `NULL` in DB     | canonical event bytes + prev_hash (hex)                                             | YES    |
| `kailash-pact/src/audit/mod.rs`          | n/a — no chain   | `canonical_json()` only — NO prev_hash linkage                                      | YES    |
| `eatp/src/ledger.rs`                     | `None`           | SHA-256 of (optional prev_hash bytes + content_json)                                | YES    |

**Drift callout** (per `rules/event-payload-classification.md` MUST
Rule 2 — cross-SDK forensic correlation requires stable fingerprints):

1. kailash-pact `TieredAuditEvent` has `content_hash()` but **no
   `prev_hash` chain field** — it is a stand-alone content hash, not a
   Merkle chain. `GovernanceDiagnostics` parity REQUIRES the chain. The
   BP-051 implementation MUST:
   - Add `prev_hash: Option<String>` field to `TieredAuditEvent` (or
     introduce a new `LinkedAuditEvent` variant in
     `kailash-pact::diagnostics`), OR
   - Delegate chain verification to `kailash-core::AuditLog` and
     document that `GovernanceDiagnostics` only reads from
     `AuditLog`-backed stores, not from `TieredAuditRouter` directly.
2. The **canonical input string** differs between kailash-py
   (`trust/audit_store.py`) and kailash-core `audit_log.rs` colon-joined
   format. If the BP intends one-to-one cross-SDK fingerprint parity
   (log emitted by Rust service, verified by Python auditor, same
   fingerprint), **a canonical-input-string reconciliation is a BP-051
   prerequisite**. This is a separate cross-SDK contract workstream that
   SHOULD be filed as its own issue before BP-051 starts.
3. The genesis sentinel differs: kailash-py uses `"0"*64`,
   kailash-core `audit_log.rs` uses `""`. EATP D6 ("semantics MUST
   match") is violated. This MUST be reconciled in BP-051.

**Recommendation**: file a sibling kailash-rs issue "Cross-SDK audit
fingerprint canonicalisation" BEFORE BP-051 is implemented. If the
fingerprints aren't identical, `GovernanceDiagnostics` has no forensic
value across SDKs.

---

## 6. Draft GitHub Issue Body (for kailash-rs)

```markdown
### MLFP Diagnostics — Rust parity for 3 of 7 helpers (cross-SDK of kailash-py#567)

The Terrene Foundation's MLFP course is upstreaming 7 diagnostics helpers
(~7,300 LOC) into the Kailash SDK. See kailash-py#567 for the full
inventory. Three of the seven have viable Rust parity today; this issue
scopes those three.

**In scope for this issue:**

1. **GovernanceDiagnostics** (~600 LOC) — read-only governance audit
   inspector. Host: `kailash-pact::diagnostics` (new module). Reuses
   SHA-256 + prev_hash chain primitives already present in
   `kailash-core::audit_log::AuditLog::verify_chain`. Python parity:
   Python `GovernanceDiagnostics` (716 LOC). **BP-051.**
2. **AgentDiagnostics + TraceEvent** (~700 LOC) — agent run capture +
   analysis (tool usage, loop detection, cost breakdown, timeline).
   Host: `kailash-kaizen::observability::diagnostics` (new module atop
   existing `Span`/`Trace`/`MetricsCollector`). Python parity:
   `AgentDiagnostics` (668 LOC) + `TraceEvent` (360 LOC). **BP-052.**
3. **RAGDiagnostics** (~700 LOC) — retrieval metrics (recall@k,
   precision@k, MRR, nDCG, context utilisation, leaderboard). Host:
   **new crate** `crates/kailash-rag-diagnostics`. Python parity:
   `RAGDiagnostics` (705 LOC). **BP-053.**

**Explicitly deferred — py-only:**

- **DLDiagnostics** (1,679 LOC) — PyTorch training instruments. No Rust
  autodiff runtime / HF-transformers equivalent in kailash-rs today.
- **InterpretabilityDiagnostics** (529 LOC) — attention heatmap, logit
  lens, linear probe, SAE. Open-weight model inspection requires
  transformers runtime; no Rust equivalent.
- **AlignmentDiagnostics** (649 LOC) — fine-tuning health (KL divergence,
  reward margin, reward hacking). No Rust alignment surface
  (kailash-align-serving hosts inference only).
- **LLMDiagnostics + JudgeCallable** (615+435 LOC) — LLM-as-judge,
  faithfulness, ROUGE/BLEU/BERTScore. No Rust judge runtime; position-swap
  bias mitigation depends on structured Delegate wrapping that lives in
  kaizen-agents but has not yet been extended to a judge harness.

**Prerequisite — cross-SDK fingerprint reconciliation:**

BP-051 depends on a canonicalisation decision across four existing chain
implementations (`kailash-core::audit_log`, `kailash-enterprise::audit`,
`kailash-pact::audit`, `eatp::ledger`). The canonical input string,
genesis sentinel, and `prev_hash` field placement currently drift.
Per `rules/event-payload-classification.md` MUST Rule 2, cross-SDK
forensic correlation requires identical fingerprints. Split this into a
sibling issue before BP-051 starts.

**Cross-SDK reference**: kailash-py#567.

**Label**: `cross-sdk`, `enhancement`, `ml`.
```

---

## 7. Go / No-Go Recommendation

| Helper                 | BP     | Go/No-go             | Blockers                                                         |
| ---------------------- | ------ | -------------------- | ---------------------------------------------------------------- |
| GovernanceDiagnostics  | BP-051 | **GO (with prereq)** | Cross-SDK fingerprint reconciliation MUST land first (see §5)    |
| AgentDiagnostics       | BP-052 | **GO**               | None — all primitives exist in `kailash-kaizen::observability`   |
| RAGDiagnostics         | BP-053 | **GO**               | Evaluate polars-rs dep cost; default to pure `serde_json` output |
| DLDiagnostics          | —      | **NO-GO (deferred)** | No Rust autodiff runtime                                         |
| InterpretabilityDiagn. | —      | **NO-GO (deferred)** | No Rust HF-transformers runtime                                  |
| AlignmentDiagnostics   | —      | **NO-GO (deferred)** | No Rust alignment surface                                        |
| LLMDiagnostics + Judge | —      | **NO-GO (deferred)** | No Rust judge runtime; Delegate-wrapped judge not yet extracted  |

**Sequence**: file fingerprint-reconciliation issue → BP-051 → BP-052 →
BP-053 (independent of 051/052). All three BPs fit within autonomous
execution cycles per `rules/autonomous-execution.md` (≤500 LOC
load-bearing logic each, ≤5 invariants each — chain verification /
span-tree traversal / metric computation are single-invariant work).
