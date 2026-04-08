# SPEC-09: Cross-SDK Parity Specification

**Status**: DRAFT
**Implements**: ADR-008 (Cross-SDK lockstep convergence)
**Cross-SDK issues**: TBD (this spec IS the governance doc for all cross-SDK work)
**Priority**: Phase 6 — validation, runs after implementation

## §1 Overview

Define the canonical type mappings, interop test vectors, and semantic contracts that BOTH Python (kailash-py) and Rust (kailash-rs) MUST satisfy per EATP D6. This spec is the **single source of truth** for cross-SDK alignment.

## §2 Canonical Type Mappings

### §2.1 MCP Protocol (per SPEC-01)

| Concept           | Python                                           | Rust                                           |
| ----------------- | ------------------------------------------------ | ---------------------------------------------- |
| Package           | `kailash_mcp`                                    | `kailash_mcp` (crate)                          |
| JSON-RPC Request  | `kailash_mcp.protocol.JsonRpcRequest`            | `kailash_mcp::protocol::JsonRpcRequest`        |
| JSON-RPC Response | `kailash_mcp.protocol.JsonRpcResponse`           | `kailash_mcp::protocol::JsonRpcResponse`       |
| JSON-RPC Error    | `kailash_mcp.protocol.JsonRpcError`              | `kailash_mcp::protocol::JsonRpcError`          |
| MCP Client        | `kailash_mcp.MCPClient`                          | `kailash_mcp::client::McpClient<T>`            |
| MCP Transport     | `kailash_mcp.transports.MCPTransport` (Protocol) | `kailash_mcp::transport::McpTransport` (trait) |
| Tool Info         | `kailash_mcp.protocol.McpToolInfo`               | `kailash_mcp::protocol::McpToolInfo`           |
| Tool Registry     | `kailash_mcp.tools.ToolRegistry`                 | `kailash_mcp::tools::ToolRegistry`             |

### §2.2 Agent Architecture (per SPEC-03, SPEC-04)

| Concept            | Python                                             | Rust                                                       |
| ------------------ | -------------------------------------------------- | ---------------------------------------------------------- |
| Agent contract     | `kaizen.core.BaseAgent(Node)`                      | `kailash_kaizen::agent::BaseAgent` (trait)                 |
| Concrete agent     | `kaizen.core.BaseAgent` (slimmed, IS the concrete) | `kaizen_agents::agent_engine::Agent` (struct)              |
| Streaming wrapper  | `kaizen_agents.StreamingAgent`                     | `kaizen_agents::streaming::StreamingAgent`                 |
| Cost wrapper       | `kaizen_agents.MonitoredAgent`                     | `kailash_kaizen::cost::MonitoredAgent`                     |
| Governance wrapper | `kaizen_agents.L3GovernedAgent`                    | `kaizen_agents::l3_runtime::L3GovernedAgent`               |
| Supervisor         | `kaizen_agents.SupervisorAgent`                    | `kaizen_agents::orchestration::SupervisorAgent`            |
| Worker             | `kaizen_agents.WorkerAgent`                        | `kaizen_agents::orchestration::WorkerAgent`                |
| Engine facade      | `kaizen_agents.Delegate`                           | `kaizen_agents::delegate_engine::DelegateEngine`           |
| TAOD loop          | `kaizen.core.AgentLoop`                            | `kaizen_agents::agent_engine::TaodRunner`                  |
| Agent posture      | `kailash.trust.posture.AgentPosture` (IntEnum)     | `kailash_kaizen::types::ExecutionMode` (expand to posture) |

### §2.3 Provider Layer (per SPEC-02)

| Concept          | Python                                          | Rust                                                              |
| ---------------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| LLM chat         | `kaizen.providers.LLMProvider` (Protocol)       | `kailash_kaizen::llm::Chat` (trait, to be added)                  |
| Streaming        | `kaizen.providers.StreamingProvider` (Protocol) | `kailash_kaizen::llm::Streaming` (trait, to be added)             |
| Embeddings       | `kaizen.providers.EmbeddingProvider` (Protocol) | `kailash_kaizen::llm::Embeddings` (trait, to be added)            |
| Cost tracking    | `kaizen.providers.CostTracker`                  | `kailash_kaizen::cost::CostTracker`                               |
| Capability flags | `kaizen.providers.ProviderCapability` (Enum)    | `kailash_kaizen::llm::ProviderCapabilities` (struct, to be added) |

### §2.4 Trust / Governance (per SPEC-07)

| Concept               | Python                                                | Rust                                             |
| --------------------- | ----------------------------------------------------- | ------------------------------------------------ |
| Constraint Envelope   | `kailash.trust.ConstraintEnvelope` (frozen dataclass) | `eatp::constraints::ConstraintEnvelope` (struct) |
| Financial dim         | `kailash.trust.FinancialConstraint`                   | `eatp::constraints::FinancialConstraint`         |
| Governance Engine     | `kailash.trust.pact.GovernanceEngine`                 | `kailash_governance::engine::GovernanceEngine`   |
| PACT Bridge           | `kailash_pact.mcp.McpGovernanceEnforcer`              | `kailash_pact::mcp::PactMcpBridge`               |
| Verification Gradient | AUTO_APPROVED → FLAGGED → HELD → BLOCKED              | Same 4 zones                                     |
| D/T/R Address         | `kailash.trust.pact.Address`                          | `kailash_governance::addressing::Address`        |

### §2.5 Events / Streaming (per SPEC-03)

| Python Event                            | Rust Event                               | Wire equivalent             |
| --------------------------------------- | ---------------------------------------- | --------------------------- |
| `TextDelta(text)`                       | `CallerEvent::Token(String)`             | Same semantic               |
| `ToolCallStart(call_id, name)`          | `CallerEvent::ToolCall(ToolCallRequest)` | Same                        |
| `ToolCallEnd(call_id, name, result)`    | `CallerEvent::ToolResult(ToolResult)`    | Same                        |
| `TurnComplete(text, usage, structured)` | `CallerEvent::Done(TaodResult)`          | Same                        |
| `BudgetExhausted(budget, consumed)`     | (via PactEngine rejection)               | Python adds to event stream |
| `ErrorEvent(error, details)`            | `CallerEvent::Error(AgentError)`         | Same                        |

## §3 Interop Test Vectors

### §3.1 JsonRpcRequest round-trip (from SPEC-01 §7)

Both SDKs produce identical JSON for the same logical request. 5 test vectors defined in SPEC-01 §7.

### §3.2 ConstraintEnvelope round-trip (from SPEC-07 §5)

Canonical JSON shape defined in SPEC-07 §5. Both SDKs must serialize/deserialize identically, including:

- `null` for absent dimensions (not omitted)
- `posture_ceiling` as lowercase string ("tool", "supervised", "autonomous")
- Finite validation on deserialization (reject NaN/Inf)

### §3.3 Agent result equivalence

Both SDKs produce semantically equivalent results for the same prompt:

```json
{
  "text": "...",
  "model": "...",
  "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
  "structured": { ... },
  "finish_reason": "stop"
}
```

Python returns `Dict[str, Any]`. Rust returns `AgentResult` struct. Field names MUST match.

## §4 Cross-SDK Issue Template

Per ADR-008 §Decision, every convergence change gets matched issues:

```markdown
Title: arch(convergence): <spec-name>
Labels: cross-sdk, convergence
Body:
Canonical spec: <link to spec in this workspace or care-eatp-co>
Cross-SDK link: <link to matched issue in other repo>
Scope: <what changes in this SDK>
Test vectors: <link to §7 interop vectors>
```

## §5 Gaps Requiring Rust Changes

| Gap                                                        | Python status         | Rust action needed                                                        |
| ---------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------- |
| `kailash-mcp` crate                                        | SPEC-01               | Create `crates/kailash-mcp/`, move kaizen MCP client, extract server base |
| Provider capability split                                  | SPEC-02               | Add `Chat`, `Streaming`, `Embeddings` traits to `kailash-kaizen/src/llm/` |
| `AgentPosture` / posture-aware validation                  | SPEC-04 + ADR-010     | Expand `ExecutionMode` to full posture spectrum on `AgentConfig`          |
| `posture_ceiling` on ConstraintEnvelope                    | SPEC-07               | Add field to `eatp::constraints::ConstraintEnvelope`                      |
| Reasoning model parameter filtering                        | SPEC-02               | Apply max_completion_tokens + strip temperature for o1/o3/o4              |
| `kailash-nodes → kailash-enterprise` inversion             | rs-core-synergy audit | Extract admin nodes to `kailash-nodes-enterprise`                         |
| MCP executor stub                                          | rs-mcp audit          | Replace simulated execution with real calls                               |
| kz MCP bridge stub                                         | rs-mcp audit          | Wire to `kailash_mcp::client::McpClient`                                  |
| Missing providers (Ollama, Cohere, HF, Perplexity, Docker) | Already in Python     | Add adapters to `kailash-kaizen/src/llm/`                                 |
| ML domain agents                                           | Already in Python     | Create `kailash-ml-agents` crate                                          |
| DriftMonitor                                               | Already in Python     | Create `kailash-ml-drift` crate                                           |
| Align fine-tuning pipeline                                 | Already in Python     | Create `kailash-align-training` crate                                     |

## §6 Verification Process

1. **Pre-implementation**: File matched `cross-sdk` issues on both repos (per ADR-008)
2. **During implementation**: Each SDK implements against this spec independently
3. **Post-implementation**: Run interop test vectors in both CIs
4. **Release**: Matched minor versions with cross-referenced release notes
5. **Ongoing**: `cross-sdk-inspection` agent checks for drift on every PR

## §7 Related Specs

All specs (SPEC-01 through SPEC-10) have cross-SDK implications documented in their respective §Rust Parallel sections. This spec aggregates the type mappings and provides the interop verification framework.

## §8 Security Considerations

Cross-SDK parity is a governance and correctness concern — but it is also a security concern. Identical-looking APIs that behave differently in edge cases create the perfect conditions for an attacker to craft inputs that one SDK accepts and the other rejects, then exploit the rejection gap.

### §8.1 Interop Test Vector Tampering

**Threat**: The interop test vectors in SPEC-01 §7 (JSON-RPC), SPEC-07 §5 (ConstraintEnvelope), and SPEC-09 §3 (AgentResult) are the single source of truth for cross-SDK wire format. If an attacker with repo write access tampers with a vector, both SDKs align to the tampered spec on the next release — and the tampering is invisible because both CIs pass. This is a classic supply-chain attack surface.

**Mitigations**:

1. Test vector files (JSON) MUST be in a dedicated directory (`workspaces/platform-architecture-convergence/01-analysis/03-specs/test-vectors/`) with an index file that hashes every vector.
2. The index hash is committed to both repos independently. Any vector modification requires updating both repos in lockstep — a single-repo PR that touches vectors fails CI on the other repo.
3. Vector modifications require a CODEOWNERS-mandated review from at least two maintainers (not one).
4. Release notes MUST explicitly list any test vector changes between releases, so downstream consumers can validate their interpretation hasn't drifted.

### §8.2 JSON Parser Differential Attacks

**Threat**: Python's `json` module and Rust's `serde_json` have subtle behavioral differences around edge cases: duplicate keys (Python uses last-wins, Rust's `serde_json::Map` behavior depends on feature flags), integer overflow (Python has arbitrary precision, Rust's `i64` overflows), trailing commas (both reject by default but can be configured), Unicode surrogate handling (differs). An attacker crafts a JSON payload that one side parses as valid and the other rejects or parses differently. In a cross-SDK system where one side validates and the other executes, this differential becomes a validation bypass.

**Mitigations**:

1. SPEC-09 §2 documents the canonical JSON parser configuration for both SDKs: `json.loads(text, strict=True)` for Python, `serde_json::from_str` with `arbitrary_precision` disabled and `preserve_order=true` for Rust.
2. A shared corpus of "differential test payloads" covers every known Python-vs-Rust JSON discrepancy. Both CIs run the corpus and assert identical parse results (value or error).
3. Integer fields MUST specify their bounds in the spec (e.g., `max_turns: i64`, `spend_limit_usd: f64 finite only`). Parsers reject out-of-range values before the values reach business logic.
4. Duplicate keys MUST be explicitly rejected by both parsers. Any canonical encoder emits keys in sorted order.

### §8.3 Cross-SDK Wire Format Drift

**Threat**: Python ships a spec change without updating Rust, or vice versa. Now one SDK encodes a new field that the other silently drops (forward-compatibility) or silently misinterprets (backward-compatibility failure). An attacker discovers the drift and uses the older-parsing side as a validation bypass: send a request the old side "approves" (missing the field that would have blocked it) and route the execution to the new side.

**Mitigations**:

1. Every wire type has a `schema_version: u32` field, verified at deserialization. Versions that do not match raise explicitly (not silently degrade).
2. Version bumps require matched releases across Python AND Rust. CI enforces version synchronization: Python's current `schema_version` must equal Rust's current `schema_version` at release time.
3. Forward-compatibility is NOT supported — a payload with `schema_version` higher than the current reader is rejected. Consumers MUST upgrade before seeing new fields.
4. A `cross-sdk-inspection` agent (referenced in SPEC-09 §6) runs on every PR and compares the Python vs Rust schema definitions, failing if they drift.

### §8.4 Streaming Event Schema Divergence

**Threat** (R2-014): Python emits `BudgetExhausted` as a typed event; Rust routes the same condition through `PactEngine rejection`. A consumer writing cross-SDK event handling sees different event types for the same condition and may miss the Rust path entirely. An attacker who can trigger budget exhaustion creates observable behavior on one side that is invisible on the other — cost overruns go unnoticed in the Rust pipeline.

**Mitigations**:

1. SPEC-09 §2.5 is updated to explicitly document streaming event schemas in canonical form. Both SDKs emit the same event types.
2. Rust's `CallerEvent` enum gains a `BudgetExhausted(BudgetInfo)` variant. Python adds a `BudgetExhausted` event on the `DelegateEvent` stream.
3. Both SDKs' event consumers receive a `BudgetExhausted` event before the stream terminates on budget violation. Consumers can distinguish "normal termination" from "budget termination" uniformly.
4. Cross-SDK interop test: trigger a known-cost workflow with a capped budget, assert both SDKs emit `BudgetExhausted` at the same point.

### §8.5 Cross-SDK Issue Template Manipulation

**Threat**: ADR-008 mandates matched `cross-sdk` issues on both repos for every convergence change. If an attacker creates an issue on one side without the matched counterpart (or with a divergent scope in the counterpart), they can push a one-sided change that claims cross-SDK justification without the cross-SDK review.

**Mitigations**:

1. A `cross-sdk-inspection` GitHub Action runs on every issue creation/modification. The action verifies the matched issue exists on the partner repo with the same labels and similar scope.
2. A matched-issue check runs at PR time: any PR that references a `cross-sdk` issue must also reference the partner repo's matched issue URL.
3. Reviewers from BOTH repos are required on `cross-sdk`-labeled PRs (enforced via CODEOWNERS).
4. Release notes for `cross-sdk` changes MUST include links to both repos' changes, verified at release time.
