# Recommendation — Cardinal decision before /todos approval

## TL;DR

**Recommend: Option A — treat the kailash-rs shipped Delegate runtime as the de facto spec for kailash-py interop.** Unblocks immediate /implement across 7 parallel-shard waves. Cardinal decision is yes/no on whether the rs-shipped implementation is the source-of-truth for kailash-py conformance.

## The cardinal question

The external **Delegate Specification v0** (Terrene, CC BY 4.0, at `~/repos/dev/unicorn-focus/drafts/02-delegate-spec-v0-outline.md`) — the document #1035 cites as authoritative — was confirmed by Agent 1 to be a **pre-draft scaffold, not a normative spec**:

- ZERO formally-defined types (~11 named artifacts, only Genesis Record has a partial proposed field list).
- NO conformance vectors enumerated.
- Conformance levels (Conforming / Partially Conforming / Non-Conforming) named but criteria undefined.
- Cross-vendor verifiability flagged as an OPEN question (§4 Q4).
- The document itself states (line 247) "if a section can only be implemented one way, it is over-specified."

Meanwhile **kailash-rs has shipped the runtime through M8-02 E2E** (13,196 LOC across 6 crates, per Agent 2), with conformance vectors defined as a Rust function `delegate_spec_vectors() -> Vec<ConformanceVector>`. The rs side is the de facto authority because it's the only place the contract is concretely defined.

**The cardinal decision:**

| Option                                                                                                                              | What it means in plain language                                                                                                                                                                                                                                        | Implication                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Mirror rs as the de facto spec** (recommended)                                                                                 | Build kailash-py to match what rs actually does, verified via shared conformance vectors vendored from rs. The "spec" is whatever rs runs today; any spec-document ambiguity is resolved by reading rs source.                                                         | Unblocks 7 shards immediately. Cross-impl conformance well-defined. Strategic implication: the document spec never becomes source-of-truth — the open-source Python impl is forever a follower of the proprietary rs impl.                        |
| **B. Pause until Delegate Spec v0 reaches normative status**                                                                        | Don't ship kailash-py Delegate until someone (Terrene Foundation) writes the actual normative spec. Today's "spec" is a sketch — building to a sketch is BLOCKED on `verify-resource-existence.md` MUST-2 (citing intent ≠ runtime).                                   | #1035 stays open indefinitely. Issue body's open-substrate argument for regulators / academics / community connectors continues to be a one-sided claim (rs has implementation, py does not). User must engage Terrene Foundation drafting cycle. |
| **C. Hybrid — ship minimum surface satisfying #1035 acceptance criteria, mark as "exploration release" pending spec normalization** | Ship `from kailash.delegate import Delegate, ConstraintEnvelope, ...` with the rs-mirrored types + conformance vectors, but flag the package version as `0.x` and the README as "exploration release; API will change when Delegate Spec v0 reaches normative status." | Compromise between A and B — half the strategic concern of A (we publicly acknowledge the spec is unsettled) with most of A's throughput.                                                                                                         |

### Pros of A (the recommendation)

- **Unblocks 7 immediate shards** — the rs side already worked through 8 milestones (M1-M8); py mirrors the proven decomposition.
- **Reuses ~80% of kailash-py's existing primitives** (per Agent 3): SPEC-07 `ConstraintEnvelope` (already canonical, with `intersect()` + `is_tighter_than()`), `TrustLineageChain` + EATP with cross-SDK `canonical_json_dumps`, `PactEngine`, `PactEatpEmitter` Protocol, the `pact/conformance/` pattern (already byte-canonical-validated against rs).
- **Cross-impl conformance is concrete** — we vendor `delegate_spec_vectors()` from rs as checked-in JSON fixtures + run them in both impls; `receipts_agree(rs, py)` proves cross-language verification (#1035's acceptance criterion).
- **Satisfies #1035's load-bearing argument** — regulator/academic/community connector author gets a runnable Apache-2.0 implementation today, not "wait for the spec to be drafted."
- **Same M-numbered shard ordering as rs** (M1 fences → M2 types → M3 trust → M4 audit → M5 dispatch → M6 runtime → M7 conformance → M8 E2E) — keeps reasoning legible to future cross-impl audits.

### Cons of A (real, not glossed)

- **The "spec" is effectively "whatever rs does today"** — rs API drift mechanically becomes py API drift. Mitigation: the `receipts_agree(rs, py)` cross-impl check catches drift; vendored vectors are the pinning surface.
- **Strategic precedent** — the Delegate Spec v0 document loses load-bearing status. Future Terrene Foundation drafting work has reduced authority because both impls predate it. This is a real institutional cost; the user should know.
- **Python impl must keep pace with rs M-numbered shards** — when rs ships M9, py must ship M9 or fall behind on conformance vectors. Ongoing maintenance commitment (per `feedback_drive_to_completion.md`).
- **Two `Delegate` classes — naming friction permanent.** `kaizen_agents.delegate.Delegate` (LLM-execution facade, 711 LOC, existing) ≠ `kailash.delegate.Delegate` (composition primitive, new). The new one CAN wire the old one as an `executor=` — but the namespace collision will confuse readers forever. Mitigation: explicit disambiguation paragraph in both classes' docstrings.
- **#1035 issue body is partially stale**: it says `Connector` is `pull/normalize/capabilities`; rs ships `authenticate/write/read/revocation`. We MUST mirror the shipped shape and amend #1035's body (or close + re-file).

### Why NOT B

B is technically clean but operationally inert. The Terrene Foundation drafting cycle is calendar-bound (per `autonomous-execution.md` § "Does NOT apply to: human-authority gates"); waiting could be months. Meanwhile rs ships through M9, M10, M11 — by the time the spec normalizes, py is so far behind the cross-impl conformance argument is purely theoretical. The user opened #1035 because the open-substrate argument needs a real implementation, not a planned one.

### Why NOT C (could be the right call if A's strategic cost is unacceptable)

C is a compromise that buys back some institutional optionality. The downside is it ships a `0.x` "exploration" badge that downstream consumers may distrust — kaizen-agents, regulators, the academic Build #14 want a stable substrate, not an exploratory one. If the user wants C, the version label and README disclaimer become load-bearing artifacts and shard M1 must include the language drafting.

## Approve Option A and proceed to /todos shard plan?

(yes / no / pick B or C with rationale)

Once approved, the next gate is `/todos` (structural human gate per `workspaces/CLAUDE.md` Phase 02) — I'll surface the 7-shard decomposition with each shard's value-anchor, mirroring rs M-numbered ordering. The decomposition is drafted at `02-plans/01-architecture.md` and `todos/active/00-shard-plan.md` already so the user can review concurrently with the cardinal decision.
