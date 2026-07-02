# Cross-SDK Protocol Upstream Donation Playbook

Operational playbook for integrating an external framework's donation into the Kailash SDK via a Protocol-based contract shared across Python and Rust. Use when an upstream contribution proposes new primitives that overlap with existing SDK primitives or depend on cross-SDK audit/event invariants.

The pattern generalizes the 7-PR integration of the MLFP diagnostics donation into kailash-py (issue #567, 2026-04-20). The worked example lives in `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md`.

## When To Use

- External framework proposes a donation of ≥1000 LOC that touches multiple sub-packages
- The donation's primitives overlap with existing SDK primitives (governance, classification, audit)
- The contribution introduces types that cross the SDK boundary (Python → Rust via shared schema)
- The Apache-licensed external codebase triggers `NOTICE` attribution (Apache 2.0 §4(d))

## The 7-Step Structure

### Step 0 — Pre-Implementation Cross-SDK Reconciliation

Before any protocol lands, every shared invariant that drifted across SDKs MUST be reconciled. Canonical-value reconciliation items (audit-chain fingerprint, event-payload format, cross-SDK classification hash) each get their own PR in the sibling SDK BEFORE the protocols land in the owner SDK.

The reconciliation PRs block the Protocol PR because the Protocol pins the shared-contract shape. Landing the Protocol before reconciliation means the sibling SDK has to re-open the contract later — an Apache-2.0-flavored way of saying "we broke the ABI."

### Step 1 — Protocols + JSON Schema (PR#0)

Land the cross-SDK contract in `src/kailash/<domain>/protocols.py` (or equivalent for Rust) with:

- Zero runtime logic (pure Protocol / trait declarations)
- Zero optional dependencies (no OpenAI, no torch, no network)
- A JSON Schema at `schemas/<concept>.v1.json` as the language-neutral source of truth

The JSON Schema's role is critical: it is the ONE document that both Python and Rust implementations validate against. If the shape drifts later, the schema is the disambiguating authority.

### Step 2 — Risk-Ascending Domain Adapters (PR#1..#N)

Per-framework concrete implementations land in risk order: easy first, hard last.

- **Risk LOW** (PR#1..#3): read-only helpers, diagnostics that just format existing telemetry
- **Risk MEDIUM** (PR#4..#5): LLM-calling adapters (judges, evaluators) — they cost money and can leak PII
- **Risk HIGH** (PR#6..#7): governance-sensitive adapters that absorb capabilities from external primitives into SDK primitives

Each adapter MUST:

1. Implement the Protocol at runtime (`isinstance` check holds in Python; `impl Trait` holds in Rust)
2. Use framework-first routing — no raw `openai`, no raw SQL, no hand-rolled dispatch
3. Ship Tier 1 unit tests AND Tier 2 integration tests with facade imports required
4. Get its own spec file in `specs/<adapter>.md` + an entry in `specs/_index.md`
5. Bump the owning sub-package's version + CHANGELOG in the SAME PR

### Step 3 — Reject Parallel Facades, Absorb Capabilities

When the external contribution includes a "DomainDiagnostics" class that duplicates SDK primitives with weaker invariants (bypasses `GovernanceEngine._lock`, non-frozen dataclasses, fail-open on errors), the PR MUST reject the parallel facade and absorb the capabilities.

Absorption means: identify the 3-5 useful capabilities in the parallel facade, add them as first-class methods on the existing SDK primitive with the SDK's thread-safety + fail-closed contracts intact. Delete the parallel facade in the same PR.

**Example — MLFP #578 PactEngine absorption:**

External contribution shipped `MLFPPactDiagnostics` with four capabilities: `snapshot()`, `evaluate()`, `diff()`, `freeze()`. The parallel facade used non-frozen dataclasses and fail-open error handling — both violate PACT invariants. PR #578 absorbed all four as methods on the existing `PactEngine`, upgraded the dataclasses to `frozen=True`, and replaced fail-open with fail-closed + audit. The external `MLFPPactDiagnostics` class was deleted in the same PR.

### Step 4 — Cross-SDK Parity Issues

For every PR that lands in one SDK, file a parity issue on the sibling SDK that references:

- The originating PR number and commit SHA
- The Protocol file and JSON Schema it implements
- The specific invariants that the sibling SDK must match (error types, fingerprint format, version bump)

The sibling SDK's implementation IS a separate PR that lands on its own cadence but MUST reference the Protocol + Schema. This prevents silent divergence during the (often weeks-long) cross-SDK implementation window.

### Step 5 — Apache Attribution (Blocker PR)

If the external contribution is Apache-2.0-licensed, root `NOTICE` gets an attribution entry per Apache 2.0 §4(d):

```
This product includes software from <Project>
(https://github.com/<org>/<repo>, Apache License 2.0).
Portions of <module-list> were adapted from <Project>'s
<specific-commit-sha>.
```

Ship attribution as a blocker PR BEFORE any adapter PR lands. A PR body that claims Apache compliance while the NOTICE is still empty ships a licensing-audit finding that costs more to clean up post-hoc than to land first.

### Step 6 — Session Planning

7 PRs ≠ 7 sessions. Parallel-worktree opportunities across different sub-packages reduce wall time:

- 3 parallel LOW-risk adapters across 3 different sub-packages = 1 session (fan-out)
- HIGH-risk PRs (governance absorption, cross-SDK fingerprint reconciliation) stay sequential — they pin invariants that the parallel adapters rely on

Apply `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination": when two parallel agents touch the same sub-package, the orchestrator designates ONE version-owner agent and tells the sibling explicitly not to touch `pyproject.toml` / `Cargo.toml` / `CHANGELOG.md`.

## Anti-Patterns

- **Protocol lands with runtime logic** — the Protocol file must be pure declarations. Logic belongs in the adapter PR.
- **Adapter ships without a spec** — `specs/_index.md` becomes stale the moment one adapter skips its entry.
- **Parallel facade absorbed in a follow-up PR** — absorption must land in the same PR that deletes the facade, or downstream consumers import the facade and build security models around it.
- **Cross-SDK parity issue filed but never referenced** — the issue is forensic evidence of the parity gap; without references in the adapter PR, the gap becomes invisible at merge time.
- **Attribution deferred "until we finalize the feature"** — Apache-2.0 §4(d) is NOT deferrable. Ship the NOTICE update first.

## Origin

kailash-py issue #567 (2026-04-20) — MLFP diagnostics donation (≈7,300 LOC across kailash-ml, kailash-kaizen, kailash-align, kailash-pact). Sessions: Session 1 (blockers + PR#0), Session 2 (PR#1), Session 3a (PR#1 gate), Session 3b (PR#2 RAG, PR#3 alignment, PR#4 interpretability, PR#7 docs parallel + PR#5 LLM-judges sequential). Outcome: 6 of 7 PRs merged in 2 sessions; PR#6 (AgentDiagnostics + TraceExporter) pending cross-SDK fingerprint acceptance (kailash-rs#468). Plan file: `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md`.
