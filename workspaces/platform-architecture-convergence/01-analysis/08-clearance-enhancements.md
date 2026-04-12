# Clearance Enhancements Analysis — 12 Issues

**Analyzed**: 2026-04-09
**Source**: GitHub issues #351, #357, #360, #365-367, #369-371, #373-375

## Executive Summary

Twelve enhancement issues span six packages (ML, Kaizen, Trust, DataFlow, Core SDK, Platform). Four overlap directly with convergence work (SPEC-04, SPEC-07, SPEC-09); three form a connected Ollama adapter cluster; two are cross-SDK labeled. Net complexity: ~10 autonomous execution cycles, most parallelizable against convergence phases.

---

## Issue-by-Issue Analysis

### #351 — docs(ml): DriftMonitor API has confusing/inconsistent surface

**Package**: kailash-ml
**Type**: Documentation / API polish
**Source file**: `packages/kailash-ml/src/kailash_ml/engines/drift_monitor.py`

**What needs to change**:

- The DriftMonitor class exposes `set_reference()`, `check_drift()`, `set_performance_baseline()`, `check_performance_degradation()`, and `schedule_monitoring()` as its public API. The issue reports that the naming is inconsistent: `set_reference` vs `set_performance_baseline` (reference vs baseline terminology), `check_drift` vs `check_performance_degradation` (asymmetric depth of naming).
- The `DriftSpec` dataclass has an `on_drift_detected` field typed as `Any` instead of a proper callback protocol, which is confusing for IDE users.
- Missing module-level docstring examples showing the happy path.

**Complexity**: 0.5 cycle (rename methods, add type alias for callback, update docstrings + examples)
**Dependencies**: None. ML package is independent from convergence.
**Risk**: LOW. Method renames require deprecation shims (ADR-009 pattern) for the old names.
**Cross-SDK**: Not applicable (kailash-ml has no Rust counterpart yet per SPEC-09 notes).

---

### #357 — BaseAgent MCP auto-discovery breaks structured output on Gemini

**Package**: kailash-kaizen
**Type**: Bug/Enhancement
**Source file**: `packages/kailash-kaizen/src/kaizen/core/mcp_mixin.py`, `packages/kailash-kaizen/src/kaizen/core/base_agent.py`

**What needs to change**:

- When MCP auto-discovery is enabled (`mcp_enabled=True`), the MCPMixin discovers tools from MCP servers and injects them into the LLM call. Gemini's `generateContent` API rejects requests that include both `tools` and `response_format` (structured output / JSON schema mode) simultaneously.
- The fix requires the MCPMixin to detect when structured output is configured (`config.response_format is not None`) and either (a) skip tool injection for that call, or (b) strip `response_format` and handle structured output parsing in the agent loop post-hoc.
- SPEC-04 BaseAgent slimming (Phase 3) is already restructuring this area: the MCPMixin and tool injection will move to composition wrappers. The fix should be applied in the current code AND the design carried forward into SPEC-04's wrapper architecture.

**Complexity**: 1 cycle
**Dependencies**: Overlaps with SPEC-04 (Phase 3). Fix should land before or concurrent with Phase 3.
**Risk**: MEDIUM. Gemini provider-specific behavior detection requires capability protocol awareness. The convergence provider split (SPEC-02) introduces per-provider capability protocols that could host this check cleanly.
**Cross-SDK**: kailash-rs does not yet have Gemini support. File cross-sdk issue for when it does.

---

### #360 — feat: publish kailash-trust shim package re-exporting kailash.trust._ under legacy eatp._ namespace

**Package**: New package (kailash-trust shim)
**Type**: Feature (backward compat)
**Source file**: `src/kailash/trust/__init__.py` and new `packages/kailash-trust-shim/`

**What needs to change**:

- The EATP SDK was merged into `kailash.trust` (completed in the `eatp-merge` workspace). External consumers who imported from `eatp.*` need a thin shim package that re-exports everything under the old namespace.
- SPEC-07 (envelope unification) is the canonical convergence spec that unifies ConstraintEnvelope types. The shim package must re-export the unified envelope, not the old scattered versions.
- Per ADR-009 Layer 1 pattern: the shim emits `DeprecationWarning` on import, re-exports via `__all__`, and is removed in v3.0.

**Complexity**: 0.5 cycle (thin package: `pyproject.toml`, `__init__.py` with re-exports, tests)
**Dependencies**: Should land AFTER SPEC-07 (Phase 2) so the envelope re-export points at the canonical type.
**Risk**: LOW. Pure re-export package with no logic.
**Cross-SDK**: Yes. Rust equivalent (`kailash-trust` crate re-exporting `eatp` symbols) needed.

---

### #365 — [kaizen-agents] No Ollama embeddings adapter

**Package**: kaizen-agents
**Type**: Feature (missing capability)
**Source file**: `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/ollama_adapter.py`

**What needs to change**:

- The existing `OllamaStreamAdapter` only supports chat completions (`/api/chat`). There is no embeddings endpoint adapter for Ollama's `/api/embed` (or `/api/embeddings` for older versions).
- The `rag_research.py` agent references embeddings but the adapter layer has no BYOK (bring-your-own-key) embeddings protocol. An `EmbeddingAdapter` protocol needs to be defined with Ollama as the first local implementation.
- The SPEC-02 provider split (Phase 2) will define per-provider capability protocols including an `EmbeddingCapability` protocol. This feature should be implemented within that structure.

**Complexity**: 1 cycle
**Dependencies**: Best implemented during or after SPEC-02 (Phase 2 provider split) so the embedding protocol lands in the right place.
**Risk**: LOW. New adapter, no breaking changes.
**Cross-SDK**: kailash-rs Ollama adapter should get embeddings too. File cross-sdk issue.

---

### #366 — [kaizen-agents] No tool-capable model allowlist

**Package**: kaizen-agents
**Type**: Feature (safety guard)
**Source file**: `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/ollama_adapter.py`

**What needs to change**:

- When tools are passed to Ollama models that do not support function calling (e.g., `phi`, `tinyllama`), the tools are silently ignored. The model returns plain text where the agent loop expects tool calls, causing silent failures.
- A tool capability registry or allowlist is needed: a mapping of Ollama model families to their capabilities (chat, tools, vision, embeddings). The adapter should raise `ModelCapabilityError` when tools are passed to a model not in the tool-capable list.
- Alternative: query Ollama's `/api/show` endpoint for model metadata to detect tool support dynamically.

**Complexity**: 1 cycle
**Dependencies**: Aligns with SPEC-02 provider capability protocols. The allowlist becomes a `ToolCapability` check in the per-provider module.
**Risk**: MEDIUM. The allowlist needs maintenance as Ollama model ecosystem evolves. Dynamic detection via `/api/show` is more robust but adds a network call.
**Cross-SDK**: Yes, same pattern needed in Rust.

---

### #367 — [kaizen-agents] OllamaStreamAdapter polish: num_predict default, kwargs options merge, synthetic tool-call ID collisions

**Package**: kaizen-agents
**Type**: Bug cluster (3 issues)
**Source file**: `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/ollama_adapter.py`

**What needs to change**:

1. **num_predict default**: The `default_max_tokens=4096` is passed as `num_predict` in Ollama options. For many small models, 4096 exceeds context window. Should default to `-1` (unlimited / model default) or detect from model metadata.
2. **kwargs options merge**: Lines 110-117 already implement kwargs merging with an allowlist (`options`, `format`, `keep_alive`, `template`). However, `options` dict values from kwargs overwrite rather than deep-merge with the base options. A user passing `kwargs={"options": {"seed": 42}}` loses the `temperature` and `num_predict` settings. Fixed: deep-merge `options` dict.
3. **Synthetic tool-call ID collisions**: Line 161 generates `f"call_ollama_{uuid.uuid4().hex[:12]}"`. The 12-hex-char truncation gives 48 bits of entropy, which is sufficient per-request but could collide across long-running sessions with thousands of tool calls. Should use full UUID or at minimum 16 hex chars.

**Complexity**: 0.5 cycle (three focused fixes in one file)
**Dependencies**: Overlaps with #363/#364 (existing Ollama bug fixes). Should be batched.
**Risk**: LOW. Contained to one adapter file.
**Cross-SDK**: Rust Ollama adapter needs equivalent fixes.

---

### #369 — feat(dataflow): FabricIntegrityMiddleware

**Package**: kailash-dataflow
**Type**: Feature (new middleware)

**What needs to change**:

- DataFlow's Fabric (data pipeline) layer currently has no middleware to detect: (a) silent bypass (a node that should go through fabric but hits the DB directly), (b) null body responses from fabric nodes, (c) direct storage access that circumvents the fabric pipeline.
- A `FabricIntegrityMiddleware` class needs to be built that intercepts fabric node execution and validates: non-null body, proper pipeline routing, no direct storage access outside the fabric path.
- This is a new class with no existing code. It follows the middleware pattern already used in DataFlow for transactions and caching.

**Complexity**: 2 cycles (new middleware + detection heuristics + tests)
**Dependencies**: None. DataFlow is not touched by convergence (per overview).
**Risk**: MEDIUM. Detection of "silent bypass" requires instrumenting the storage layer, which could affect performance.
**Cross-SDK**: Rust DataFlow does not exist yet. No cross-sdk needed now.

---

### #370 — feat(core): EventLoopWatchdog

**Package**: Core SDK
**Type**: Feature (new diagnostic primitive)

**What needs to change**:

- In production async deployments (Nexus, DataFlow async), event loop stalls caused by blocking calls are a common silent failure. Currently, the only detection is when requests timeout.
- An `EventLoopWatchdog` class needs to be built that: (a) periodically schedules a callback at a known interval, (b) detects when the callback fires late (beyond threshold, e.g., >100ms stall), (c) emits a structured WARN log with stack trace of the blocking call, (d) optionally raises or metrics-emits.
- Similar to `asyncio`'s debug mode but with structured logging and configurable thresholds.

**Complexity**: 1 cycle
**Dependencies**: None. Core SDK module, standalone.
**Risk**: LOW. Diagnostic-only, no production path changes.
**Cross-SDK**: Yes. Rust `tokio` has similar instrumentation but the API should be semantically matched.

---

### #371 — feat(kaizen): OntologyRegistry

**Package**: kailash-kaizen
**Type**: Feature (new primitive)

**What needs to change**:

- A classification primitive that uses embedding similarity to classify concepts against a registered ontology. Example: classify a user message as belonging to domain categories ("billing", "technical", "shipping") using embedding vectors rather than keyword matching or LLM calls.
- The registry stores concept labels with their embedding vectors. Classification is a nearest-neighbor lookup in embedding space.
- Must integrate with the embeddings adapter path (connects to #365 -- Ollama embeddings adapter).
- Per `rules/agent-reasoning.md`, this is a permitted deterministic structure (it is a tool/data endpoint, not agent decision logic) -- the LLM can use the classification result as input to its reasoning.

**Complexity**: 2 cycles (embedding storage, similarity search, API design, tests)
**Dependencies**: Requires an embeddings adapter (#365). The SPEC-02 provider split defines where embeddings live.
**Risk**: MEDIUM. New primitive with no existing code. API design needs care to avoid becoming a keyword-matching replacement (which would violate agent-reasoning rules).
**Cross-SDK**: Yes. Concept classification is a cross-SDK primitive.

---

### #373 — feat(dataflow): BulkResult MUST auto-emit WARN on partial failure

**Package**: kailash-dataflow
**Type**: Feature (observability enforcement)

**What needs to change**:

- Per `rules/observability.md` Rule 6, bulk operations MUST emit WARN when `failed > 0`. The rule explicitly cites `BulkCreate._handle_batch_error()` as having `except Exception: continue` with zero logging.
- There is currently NO `BulkResult` dataclass in the DataFlow source. The bulk nodes return raw dicts.
- The fix: (a) create a `BulkResult` dataclass per the pattern in `guides/deterministic-quality/06-observability-primitives.md`, (b) have its `__post_init__` emit the WARN log, (c) update all 4 bulk node types (`BulkCreatePoolNode`, `BulkUpsertNode`, and their non-pool variants) to return `BulkResult` instead of raw dicts.
- Also fix the `except Exception: continue` pattern to include a WARN log.

**Complexity**: 1 cycle
**Dependencies**: None. DataFlow is independent from convergence.
**Risk**: LOW-MEDIUM. Return type change from dict to `BulkResult` could break callers that expect raw dicts. Must preserve `.to_dict()` compatibility.
**Cross-SDK**: Yes, labeled `cross-sdk`. Rust bulk operations need the same WARN contract.

---

### #374 — feat(core): ProgressUpdate contract for long-running node operations

**Package**: Core SDK
**Type**: Feature (new protocol)

**What needs to change**:

- Long-running nodes (ML training, bulk operations, data migrations) currently have no way to report progress to the runtime. The runtime treats them as black boxes until completion.
- A `ProgressUpdate` protocol/dataclass needs to be defined: `(node_id, percent_complete, message, estimated_remaining_seconds)`.
- Nodes opt in by yielding `ProgressUpdate` from their execution. The runtime collects and exposes progress through the `EventEmitterMixin` (which already exists at `src/kailash/nodes/mixins/event_emitter.py`).
- Existing `progress_callback` patterns in the edge migration code suggest partial prior art but no unified contract.

**Complexity**: 1.5 cycles (protocol definition, runtime integration, opt-in for ML/DataFlow nodes)
**Dependencies**: None directly, but the protocol should align with SPEC-08 (Core SDK consolidation) registry patterns.
**Risk**: MEDIUM. Changes to the node execution contract affect the runtime hot path. Must be opt-in, not mandatory.
**Cross-SDK**: Yes, labeled `cross-sdk`. Rust node trait needs matching `ProgressUpdate` type.

---

### #375 — feat(platform): cross-SDK API parity check tooling

**Package**: Platform (tooling)
**Type**: Feature (CI infrastructure)

**What needs to change**:

- Existing parity tooling at `tests/parity/utils/` only checks sync/async runtime method parity within Python. There is no cross-SDK (Python vs Rust) parity checker.
- SPEC-09 (Phase 6) defines cross-SDK interop test vectors. This issue requests automated tooling that: (a) extracts the public API surface from both SDKs (Python via `inspect`, Rust via `cargo doc --document-private-items` JSON output), (b) compares method names, type signatures, and module structure, (c) generates a parity report highlighting gaps.
- The convergence Phase 6 (`10-phase6-crosssdk.md`) already plans interop test vectors and CI jobs. This tooling augments that with API surface comparison.

**Complexity**: 2 cycles (Python API extractor, Rust API extractor, comparison engine, report generator)
**Dependencies**: Should land during or after Phase 6 (SPEC-09). Requires access to both repos.
**Risk**: LOW. Tooling-only, no production code changes.
**Cross-SDK**: IS the cross-SDK effort.

---

## Dependency Map

```
Convergence Phase 2 (SPEC-02 Provider Split)
    ├── #365 (Ollama embeddings) — needs EmbeddingCapability protocol
    ├── #366 (tool allowlist) — needs ToolCapability protocol
    └── #357 (Gemini structured output) — needs per-provider capability detection

Convergence Phase 2 (SPEC-07 Envelope Unification)
    └── #360 (trust shim) — must re-export canonical envelope

Convergence Phase 3 (SPEC-04 BaseAgent Slim)
    └── #357 (Gemini fix) — MCPMixin restructuring

Convergence Phase 6 (SPEC-09 Cross-SDK)
    └── #375 (parity tooling) — augments interop test infrastructure

Independent (no convergence dependency):
    #351 (DriftMonitor docs)
    #367 (Ollama adapter polish)
    #369 (FabricIntegrityMiddleware)
    #370 (EventLoopWatchdog)
    #373 (BulkResult WARN)
    #374 (ProgressUpdate)

#365 → #371 (OntologyRegistry depends on embeddings adapter)
```

## Risk Register

| Issue | Risk Level  | Likelihood | Impact | Mitigation                                                         |
| ----- | ----------- | ---------- | ------ | ------------------------------------------------------------------ |
| #357  | Major       | High       | High   | Gemini users hit this in production. Fix before Phase 3.           |
| #366  | Major       | High       | Medium | Silent tool drops cause agent failures. Allowlist + loud error.    |
| #369  | Significant | Medium     | Medium | Performance impact of storage instrumentation. Benchmark required. |
| #371  | Significant | Medium     | Medium | API design risk -- must not become keyword-matching replacement.   |
| #374  | Significant | Medium     | Medium | Runtime hot path change. Must be strictly opt-in.                  |
| #360  | Minor       | Low        | Low    | Pure re-export, minimal risk. Timing dependency on SPEC-07.        |
| #351  | Minor       | Low        | Low    | Docs-only. No production risk.                                     |
| #367  | Minor       | Low        | Low    | Three small fixes in one file.                                     |
| #370  | Minor       | Low        | Low    | Diagnostic-only primitive.                                         |
| #373  | Minor       | Low        | Medium | Return type change needs backward compat.                          |
| #375  | Minor       | Low        | Low    | Tooling-only, no production impact.                                |

## Execution Grouping

**Group A — Implement now (independent, no convergence blocker):**

- #351 DriftMonitor docs (0.5 cycle)
- #367 Ollama adapter polish (0.5 cycle)
- #370 EventLoopWatchdog (1 cycle)
- #373 BulkResult WARN (1 cycle)

**Group B — Implement with convergence Phase 2:**

- #365 Ollama embeddings (1 cycle, needs SPEC-02 EmbeddingCapability)
- #366 Tool allowlist (1 cycle, needs SPEC-02 ToolCapability)
- #357 Gemini fix (1 cycle, overlaps SPEC-02 + SPEC-04)
- #360 Trust shim (0.5 cycle, needs SPEC-07 done)

**Group C — Implement with convergence Phase 5+:**

- #369 FabricIntegrityMiddleware (2 cycles, independent but large)
- #374 ProgressUpdate (1.5 cycles, aligns with SPEC-08 patterns)

**Group D — Implement with convergence Phase 6:**

- #375 Cross-SDK parity tooling (2 cycles, IS Phase 6 augmentation)
- #371 OntologyRegistry (2 cycles, needs #365 first)

**Total**: ~14 autonomous execution cycles. With parallelization against convergence phases, wall-clock addition is ~4-6 cycles beyond the convergence plan.
