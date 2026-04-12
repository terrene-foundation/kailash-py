# ADR-008: Cross-SDK Lockstep Convergence

**Status**: ACCEPTED (2026-04-07)
**Scope**: Governance process — applies to all ADRs and SPECs
**Deciders**: Platform Architecture Convergence workspace

## Context

Per EATP D6 (cross-SDK convention): **"Both SDKs implement features independently. Semantics MUST match."** The convergence work in this workspace crosses both Python (kailash-py) and Rust (kailash-rs) SDKs. Without explicit lockstep coordination, the two SDKs will diverge during the refactor:

1. **Python refactors MCP into `packages/kailash-mcp/`** while Rust stays fragmented → Python client can't reliably talk to Rust servers.
2. **Rust extracts `crates/kailash-mcp/`** with slightly different JSON-RPC field naming than Python → cross-SDK interop breaks.
3. **Python unifies ConstraintEnvelope** while Rust keeps 3 variants → serialized envelopes don't round-trip.
4. **Python slims BaseAgent** differently than Rust's BaseAgent trait → semantic differences in how tools are attached, how Signatures flow, how streaming events are emitted.

The red team flagged this in round 1, item #6:

> "Cross-SDK lockstep assumes synchronized release cadences. Python and Rust have independent CI, release branches, downstream consumers. A semantic divergence introduced during the race is exactly the EATP D6 violation the convergence is trying to eliminate."

## Decision

**Every convergence change that touches cross-SDK semantics MUST be governed by a shared canonical spec document, filed as matched GitHub issues on BOTH repos with the `cross-sdk` label BEFORE implementation begins in either repo.**

### The lockstep protocol

For every architectural change in this workspace that affects cross-SDK semantics:

#### 1. Write canonical spec FIRST

- Location: `docs/specs/<spec-name>.md` in the `terrene-foundation/care-eatp-co` repo (or this workspace's `03-specs/` while in-flight)
- Contents: wire types, semantics, invariants, backward compat rules, test vectors
- Reviewed by platform-architecture-convergence workspace BEFORE any code change

#### 2. File matched GitHub issues

Two issues (one per repo) with:

- **Identical title**: `arch(convergence): <spec-name>` (exactly the same on both repos)
- **Body cross-references**: each issue links to the other
- **Label**: `cross-sdk` on both
- **Label**: `convergence` on both
- **Link to the canonical spec document**

Example:

```
# terrene-foundation/kailash-py/issues/XXX
Title: arch(convergence): extract kailash-mcp package
Labels: cross-sdk, convergence

Canonical spec: https://github.com/terrene-foundation/care-eatp-co/blob/main/docs/specs/kailash-mcp.md

Cross-SDK link: esperie-enterprise/kailash-rs#YYY

## Scope
- Create packages/kailash-mcp/
- Move src/kailash/mcp_server/* to packages/kailash-mcp/src/kailash_mcp/
- Unify JsonRpcRequest/Response/Error types per spec
- Add backward-compat shims at src/kailash/mcp_server/*
- Interop test vectors must pass (see spec §7)
```

```
# esperie-enterprise/kailash-rs/issues/YYY
Title: arch(convergence): extract kailash-mcp package
Labels: cross-sdk, convergence

Canonical spec: https://github.com/terrene-foundation/care-eatp-co/blob/main/docs/specs/kailash-mcp.md

Cross-SDK link: terrene-foundation/kailash-py#XXX

## Scope
- Create crates/kailash-mcp/
- Move crates/kailash-kaizen/src/mcp/* to crates/kailash-mcp/
- Extract McpServerCore trait from nexus, eatp, trust-plane
- Unify JsonRpcRequest/Response/Error types per spec
- Refactor nexus, eatp, trust-plane to use shared server base
- Interop test vectors must pass (see spec §7)
```

#### 3. Implement against the spec — NOT against the other repo's code

Both SDKs implement the spec **independently**. Neither implementation references the other's file structure or class names directly. The spec is the single source of truth.

**Why**: If Python implementation waits for Rust, or vice versa, the convergence stalls on synchronization. Both can proceed in parallel as long as both implement the canonical spec.

#### 4. Validate via round-trip interop tests

Every spec includes **test vectors** — canonical JSON blobs that both SDKs must produce and consume identically.

Example (from kailash-mcp spec):

````markdown
## §7 Interop Test Vectors

### 7.1 JsonRpcRequest (basic)

Both SDKs MUST produce this exact JSON when serializing:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": { "path": "/tmp/x.txt" }
  },
  "id": 42
}
```
````

And MUST parse it into equivalent native types (Python `JsonRpcRequest` and Rust `JsonRpcRequest`).

Test: `test_jsonrpc_request_basic_roundtrip` (in both SDKs)

````

Round-trip tests run in both CI systems:
- **Python**: deserializes Rust-produced JSON, re-serializes, compares byte-for-byte
- **Rust**: deserializes Python-produced JSON, re-serializes, compares byte-for-byte
- **Cross-SDK**: Python produces, Rust consumes and produces, Python compares

#### 5. Release coordination

Both SDKs ship the convergent change in matched minor versions:

- Python `kailash-mcp 0.1.0` + `kailash 2.8.0` (shim added)
- Rust `kailash-mcp 0.1.0` + `kailash-core 0.X.0`
- Release notes on both repos cross-reference each other

Version numbers do NOT need to match. Release dates should be within the same week (ideally same day). The `cross-sdk` label triggers a release-coordination checklist.

#### 6. Deprecation windows match

Both SDKs deprecate old import paths in the same minor version and remove them in the same major version (see ADR-009).

### Governance rules

**MUST**:

1. Every convergence PR in either repo MUST link to the canonical spec document in its description.
2. Every convergence PR MUST reference the matched issue in the OTHER repo's `Fixes #N` or `Related to <repo>#N` field.
3. Every convergence PR MUST add or update interop test vectors per the spec.
4. Release notes MUST cross-link the matched release in the other repo.
5. Specs with `status: DRAFT` cannot have implementation PRs merged in either repo.
6. Specs move to `status: ACCEPTED` only after review in the platform-architecture-convergence workspace.

**MUST NOT**:

1. Implementation code in Python MUST NOT reference Rust file paths or type names directly (use the spec terminology).
2. Implementation code in Rust MUST NOT reference Python module paths or class names directly.
3. Changes to the canonical spec MUST NOT be made in only one SDK's PR — spec changes require a separate PR to the spec repo.
4. A `cross-sdk` issue MUST NOT be closed until the matched issue in the other repo is also closed.

## Rationale

1. **EATP D6 compliance is non-negotiable.** The whole point of cross-SDK work is that both implementations behave identically. Without lockstep governance, they drift.

2. **Avoids the "who changes first" deadlock.** Both SDKs implement against the spec independently. No serialization penalty.

3. **Interop tests are verification, not coordination.** The test vectors in the spec become the contract. If both SDKs pass the same tests, they interop.

4. **Independent CI/release cadence is preserved.** Python's CI and Rust's CI don't need to be coupled. Each SDK releases when its own work is done. The only coupling is at the release-notes level (cross-reference).

5. **Canonical spec in care-eatp-co repo** is the right home — that repo already owns cross-SDK specifications (EATP, CARE, CO). The convergence specs fit naturally there.

6. **Cross-SDK label is discoverable.** Issue filters on `cross-sdk` label (already in use per `rules/cross-sdk-inspection.md`) make audit straightforward.

## Consequences

### Positive

- ✅ EATP D6 semantic parity guaranteed by construction
- ✅ Cross-SDK interop tests provide continuous verification
- ✅ Independent release cadences preserved
- ✅ Spec changes are deliberate and reviewed
- ✅ Matched issues create audit trail
- ✅ Implementation can proceed in parallel across both SDKs
- ✅ Fits into existing `rules/cross-sdk-inspection.md` process

### Negative

- ❌ Requires writing spec documents BEFORE implementation (adds up-front work)
- ❌ Requires discipline to keep specs and issues in sync
- ❌ Release coordination adds process overhead (~30min per convergent release)
- ❌ Interop test infrastructure must exist in both repos' CI

### Neutral

- Specs live in `workspaces/platform-architecture-convergence/01-analysis/03-specs/` during the convergence work, then migrate to `care-eatp-co/docs/specs/` at codify time.
- `cross-sdk` label and process already exist — this ADR formalizes the lockstep requirement.
- Release cross-references are a manual step; automation can be added later (release-specialist agent could generate the cross-reference block).

## Alternatives Considered

### Alternative 1: Python goes first, Rust catches up later

**Rejected**. Rust will have to match Python's choices, removing Rust's agency. If Python makes an incorrect choice, Rust inherits the mistake. And Rust is ahead on agent architecture — Python should learn from Rust there, not the other way around.

### Alternative 2: Rust goes first, Python catches up later

**Rejected**. Symmetric problem. Also, Rust's release cadence is slower (compile times, stricter typing), so blocking Python on Rust would stall the convergence.

### Alternative 3: No formal coordination — just file issues and trust teams

**Rejected**. This is the current state and it has already produced 3 different ConstraintEnvelope types in Python alone. Without governance, drift is inevitable.

### Alternative 4: Merge the two SDKs into a single polyglot repo

**Rejected**. Outside the scope of this workspace. Would be a massive reorganization affecting external consumers, CI, release pipelines, documentation.

## Implementation Notes

### Spec document template

Every canonical spec follows this template:

```markdown
# <Name> Specification

**Status**: DRAFT | ACCEPTED | SUPERSEDED
**Version**: X.Y.Z
**Last updated**: YYYY-MM-DD
**Implements**: <ADR reference>
**Matched issues**:
- Python: terrene-foundation/kailash-py#NNN
- Rust: esperie-enterprise/kailash-rs#NNN

## §1 Overview
<2-3 paragraphs: what this spec covers>

## §2 Wire Types
<canonical type definitions in both Python and Rust syntax>

## §3 Semantics
<behavior rules, invariants, error cases>

## §4 Backward Compatibility
<shim rules, deprecation path>

## §5 Security Considerations
<threat model, input validation rules>

## §6 Examples
<usage examples showing intended API>

## §7 Interop Test Vectors
<canonical JSON blobs + expected parse results>

## §8 Implementation Notes
<non-normative guidance for implementers>

## §9 Related Specs
<links to other specs this depends on or supersedes>
````

### Release coordination checklist

Added to `release-specialist` agent instructions for `cross-sdk` labeled releases:

- [ ] Matched issue in other repo is also ready for release
- [ ] Release notes in both repos cross-reference each other
- [ ] Interop test vectors pass in both CI systems
- [ ] Spec document status is ACCEPTED (not DRAFT)
- [ ] Version numbers follow the spec's compatibility matrix
- [ ] Deprecation warnings added in this release for any removal scheduled in the next major version
- [ ] `cross-sdk` label removed from both issues after release (moved to `released` label)

### Enforcement

The `cross-sdk-inspection` agent and the `reviewer` agent are updated to check:

1. Every PR with `cross-sdk` label has the matched-repo reference in its description
2. Every PR touching MCP, providers, trust, PACT, agents, or Delegate is checked for cross-SDK impact
3. Every release with `cross-sdk` label triggers the coordination checklist

### Initial list of cross-SDK specs (to be written during this workspace)

Per SPEC-09:

| Spec                                    | Python impl                                                                  | Rust impl                              | Status |
| --------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------- | ------ |
| SPEC-01: kailash-mcp package            | `packages/kailash-mcp/`                                                      | `crates/kailash-mcp/`                  | DRAFT  |
| SPEC-02: Provider layer                 | `kaizen/providers/`                                                          | `kailash-kaizen/src/llm/`              | DRAFT  |
| SPEC-03: Composition wrappers           | `kaizen_agents/{streaming,monitored,l3_governed,supervisor,worker}_agent.py` | `kaizen-agents/src/{streaming,...}`    | DRAFT  |
| SPEC-04: BaseAgent slimming             | `kaizen/core/base_agent.py`                                                  | `kailash-kaizen/src/agent/mod.rs`      | DRAFT  |
| SPEC-05: Delegate facade                | `kaizen_agents/delegate.py`                                                  | `kaizen-agents/src/delegate_engine.rs` | DRAFT  |
| SPEC-06: Nexus auth migration           | `packages/kailash-nexus/src/nexus/auth/`                                     | `crates/kailash-nexus/src/auth/`       | DRAFT  |
| SPEC-07: ConstraintEnvelope unification | `kailash.trust.envelope`                                                     | `eatp::constraints`                    | DRAFT  |
| SPEC-08: Core SDK audit consolidation   | `kailash.trust.audit_store`                                                  | `eatp::audit`                          | DRAFT  |
| SPEC-09: Cross-SDK parity               | (this governance doc)                                                        | (this governance doc)                  | DRAFT  |
| SPEC-10: Multi-agent patterns           | `kaizen_agents/patterns/`                                                    | `kaizen-agents/src/orchestration/`     | DRAFT  |

All specs must reach ACCEPTED status before `/todos` phase begins.

## Related ADRs

- **ADR-001 through ADR-007**: every earlier ADR's implementation is governed by this lockstep protocol
- **ADR-009**: Backward compatibility strategy (matched deprecation windows)

## Related Documents

- `rules/cross-sdk-inspection.md` — existing governance rule for cross-SDK issue filing
- `rules/independence.md` — Foundation independence (no commercial references in specs)
- `rules/autonomous-execution.md` — convergence work uses autonomous execution model
