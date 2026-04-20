# Issue #567 — Synthesized Proposal (ultrathink team)

**Date:** 2026-04-20
**Team:** pattern-expert, OSS-strategist, analyst, pact-specialist, kaizen-specialist (+ kailash-rs parity analyst)
**Status:** Proposal — awaiting user decision

## One-line recommendation

**Option E — "3 primitives + 4 domain adapters + 1 engine-extension + 1 rejection"**, shipped via a foundation PR followed by 7 risk-ascending domain PRs across ~5-6 autonomous cycles.

## Why Option E beats the alternatives

| Alternative                                             | Why rejected                                                                                                                                             |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A — 7 direct upstreams** (issue body default)         | No shared contract. Every future diagnostic re-litigates architecture. GovernanceDiagnostics duplicates PACT.                                            |
| **B — single `Diagnostic` ABC in a shared location**    | Rigid inheritance breaks on helpers with genuinely different shapes. Doesn't address the `TraceEvent` / `JudgeCallable` cross-cutting problem.           |
| **C — new `kailash-diagnostics` cross-cutting package** | Premature 9th framework. Carries plotly/polars deps for every user. Use only as Option-E escape hatch if core protocols grow runtime logic.              |
| **E (chosen)**                                          | Protocols in core SDK (zero runtime logic, zero optional deps). Adapters land where `rules/framework-first.md` says they belong. 8th helper is additive. |

## The architecture

### Three primitives in core SDK (`src/kailash/diagnostics/protocols.py`)

**Protocol-only** — `typing.Protocol` + dataclass schemas. Zero runtime logic. Zero optional deps. Cross-SDK definitive.

```python
# src/kailash/diagnostics/protocols.py  (PR#0, ~150 LOC total)

@dataclass(frozen=True)
class TraceEvent:
    event_id: str
    event_type: Literal["agent.run.start", "agent.run.end", "agent.step",
                        "tool.call.start", "tool.call.end",
                        "llm.call.start", "llm.call.end",
                        "judge.verdict", "loop.suspected",
                        "budget.exceeded", "error"]
    timestamp: datetime          # UTC, ISO-8601 "+00:00"
    run_id: str
    agent_id: str
    cost_microdollars: int       # aligned with kaizen.cost.tracker (not legacy float)
    parent_event_id: Optional[str] = None
    trace_id: Optional[str] = None      # OTel correlation
    span_id: Optional[str] = None
    tenant_id: Optional[str] = None
    envelope_id: Optional[str] = None   # PACT envelope correlation
    tool_name: Optional[str] = None
    llm_model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    duration_ms: Optional[float] = None
    status: Optional[Literal["ok", "error", "cancelled"]] = None
    payload_hash: Optional[str] = None  # "sha256:XXXXXXXX" per event-payload-classification §2
    payload: Optional[dict] = None

class JudgeCallable(Protocol):
    async def __call__(self, input: JudgeInput) -> JudgeResult: ...

@dataclass(frozen=True)
class JudgeInput:
    prompt: str
    candidate_a: str
    candidate_b: Optional[str] = None    # None = pointwise; set = pairwise
    reference: Optional[str] = None
    rubric: Optional[str] = None          # free-form; NO hardcoded taxonomy

@dataclass(frozen=True)
class JudgeResult:
    score: Optional[float]
    winner: Literal["A", "B", "tie", None]
    reasoning: Optional[str]
    judge_model: str
    cost_microdollars: int
    prompt_tokens: int
    completion_tokens: int

class Diagnostic(Protocol):
    """Context manager + report() + optional plot(). run_id for correlation."""
    run_id: str
    def __enter__(self) -> "Diagnostic": ...
    def __exit__(self, *exc) -> None: ...
    def report(self) -> dict: ...
    # plot() is NOT in the protocol — lives on concrete classes, gated by [plot] extra
```

Companion: **`schemas/trace-event.v1.json`** — language-neutral JSON Schema; the one-true cross-SDK contract. Rust parity MUST read this file.

### Four domain adapters (concrete in their domain packages)

| Helper                      | Package / location                      | Implements   | Cleanup burden                                                           |
| --------------------------- | --------------------------------------- | ------------ | ------------------------------------------------------------------------ |
| DLDiagnostics               | `kailash_ml.diagnostics.DLDiagnostics`  | `Diagnostic` | Rename medical metaphors; matplotlib/plotly in `ml[dl]` extras           |
| RAGDiagnostics              | `kailash_ml.diagnostics.RAGDiagnostics` | `Diagnostic` | No new deps (pure IR math); namespace under kailash_ml.diagnostics.rag   |
| InterpretabilityDiagnostics | `kaizen.interpretability`               | `Diagnostic` | New `kaizen[interpretability]` extras; transformers pinned `>=4.40,<5.0` |
| AlignmentDiagnostics        | `kailash_align.diagnostics`             | `Diagnostic` | Drop `trl` fallback (numpy closed-form KL already in code)               |

### One engine-extension + one rejection (PACT side)

**REJECT** MLFP's `GovernanceDiagnostics` (716 LOC parallel facade) — 3 MUST violations (bypasses `GovernanceEngine._lock`, non-frozen `GovernanceContext`, fails-open drill probes).

**Absorb** four capabilities as first-class `GovernanceEngine` methods:

```python
# packages/kailash-pact/src/kailash_pact/governance/engine.py
engine.verify_audit_chain(*, tenant_id=None, start_sequence=0, end_sequence=None,
                          since=None, until=None) -> ChainVerificationResult
engine.envelope_snapshot(*, envelope_id=None, role_address=None,
                         at_timestamp=None, tenant_id=None) -> EnvelopeSnapshot
engine.iter_audit_anchors(*, tenant_id=None, since=None, until=None,
                          limit=10_000) -> Iterator[AuditAnchor]

# packages/kailash-pact/src/kailash_pact/costs/tracker.py
tracker.consumption_report(*, since=None, until=None,
                            envelope_id=None, agent_id=None) -> ConsumptionReport

# packages/kailash-pact/src/kailash_pact/governance/testing.py (test-only namespace)
run_negative_drills(engine, drills, *, stop_at_first_failure=False)
    -> list[NegativeDrillResult]
```

All methods acquire `self._lock` (MUST #8). All result dataclasses `frozen=True` (MUST #1). `verify_audit_chain` never raises on chain break — returns `is_valid=False` with `first_break_reason` (fail-closed, MUST #4).

### Two framework-first corrections (mandatory Kaizen refactors)

1. **LLMDiagnostics/JudgeCallable `_parse_score()` regex** → structured Signature OutputField. BLOCKED by `rules/agent-reasoning.md` MUST Rule 3 as-is.
2. **AgentDiagnostics Langfuse import** → `TraceExporter` Protocol with in-tree `NoOpTraceExporter` + `JsonlTraceExporter`. Third-party exporters live in user code. (Good news: Langfuse is NOT in any current `pyproject.toml`; strip at adoption is clean.)

### One namespace hygiene clean-up

ROUGE / BLEU / BERTScore → `kaizen.evaluation.*` (NOT `kaizen.judges.*`). Algorithmic metrics don't share the LLM/cost/budget surface that `kaizen[judges]` extras carry.

## Pre-implementation blockers (MUST land before PR#0)

| #      | Blocker                                                                                                                                                                                                                                                                                                                                                                                                                                 | Owner                                 | Est.      |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | --------- |
| **B1** | **Cross-SDK fingerprint reconciliation** — 4 Rust audit-chain impls drifted (`kailash-core::audit_log`, `kailash-enterprise::audit::sqlite`, `kailash-pact::audit`, `eatp::ledger`); Python uses `"genesis"` sentinel, Rust uses `""`/`"0"*64`/`None`. Canonical spec: genesis `"0"*64`, colon-delimited canonical input, `+00:00` timestamp, `hmac.compare_digest` verify. **File issue in `esperie/kailash-rs` BEFORE BP-051 starts** | kailash-rs reviewer + pact-specialist | 1 session |
| **B2** | **kailash-py genesis sentinel alignment** — `src/kailash/trust/pact/audit.py:179` uses `"genesis"`; update to `"0"*64` with Tier 2 round-trip test per `rules/orphan-detection.md` §2a                                                                                                                                                                                                                                                  | pact-specialist                       | 2 hours   |
| **B3** | **`CostTracker._history` extension** — add `envelope_id` + `agent_id` fields (currently only `amount/description/timestamp/cumulative`); required by `consumption_report`                                                                                                                                                                                                                                                               | pact-specialist                       | 2 hours   |
| **B4** | **NOTICE file attribution** — root `NOTICE` needs MLFP attribution per Apache 2.0 §4(d)                                                                                                                                                                                                                                                                                                                                                 | any                                   | 15 min    |

## PR shape — 8 PRs, 5-6 sessions

```
Session 1: BLOCKERS
  ├── B1 — kailash-rs fingerprint reconciliation issue filed + accepted
  ├── B2 — kailash-py genesis sentinel alignment
  ├── B3 — CostTracker _history extension
  └── B4 — NOTICE file attribution

Session 2: PR#0 (foundation, blocks everything)
  └── src/kailash/diagnostics/protocols.py + schemas/trace-event.v1.json

Session 3-5: Risk-ascending domain PRs (parallel where version-owners differ)
  ├── PR#1 — DLDiagnostics  → kailash_ml.diagnostics.DLDiagnostics     [LOW]
  ├── PR#2 — RAGDiagnostics → kailash_ml.diagnostics.RAGDiagnostics    [LOW]
  ├── PR#3 — AlignmentDiagnostics → kailash_align.diagnostics          [LOW-MED]
  ├── PR#4 — InterpretabilityDiagnostics → kaizen.interpretability     [MED]
  ├── PR#5 — LLMDiagnostics + JudgeCallable impl → kaizen.judges       [MED-HIGH]
  │          (+ ROUGE/BLEU → kaizen.evaluation namespace)
  ├── PR#6 — AgentDiagnostics + TraceExporter → kaizen.observability   [HIGH]
  │          (requires completed B1 for cross-SDK TraceEvent fingerprint)
  └── PR#7 — GovernanceEngine method extensions → kailash_pact         [HIGH]
             (NOT MLFP's GovernanceDiagnostics — that is REJECTED)

Session 6: Cross-SDK parity (kailash-rs)
  ├── BP-051 — GovernanceEngine chain-verify / envelope-snapshot parity
  ├── BP-052 — TraceEvent + Kaizen-rs observability parity
  └── BP-053 — RAGDiagnostics-rs (new crate or kaizen-rs::rag_metrics)
```

**Parallel opportunities per `rules/agents.md` MUST Parallel-Worktree Package Ownership:**

- Session 3: PR#1 (kailash-ml owner A) || PR#3 (kailash-align owner B) || PR#4 (kaizen owner C) — 3 agents, 3 different version owners
- Session 4: PR#2 (kailash-ml owner) sequential after PR#1 merges (same pyproject); PR#5 || PR#7 (different packages)
- Session 5: PR#6 (kaizen) — sequential after PR#5, same pyproject

## Gate exit criteria per PR

Each PR MUST satisfy before merge:

1. 3-tier tests green (Tier 1 unit + Tier 2 real infra + Tier 3 E2E where applicable)
2. Cross-SDK parity issue filed + acknowledged in kailash-rs
3. Spec updated — `specs/diagnostics-catalog.md` appended + full sibling-spec sweep per `rules/specs-authority.md` 5b
4. `grep -ri 'stethoscope\|x-ray\|ECG\|flight recorder' packages/<pkg>/ → empty` (medical metaphor regression)
5. Tier 2 test via framework facade (`from kailash.diagnostics import DLDiagnostics`), NOT direct module import
6. 2-week soak in main before next gate in the sequence

## Strategic consequences

**Donation governance:** MLFP is Foundation-owned, same arm's-length contributor terms as any. No CLA complication. Post-merge Kailash owns maintenance; MLFP is a downstream user like anyone else. No partnership entanglement. ✓ `rules/independence.md`

**SemVer:** Core protocols (PR#0) ship as **stable** on merge (instability in the contract defeats cross-SDK parity). Domain adapters ship at sub-package minor-bump cadence (kailash-ml 0.16/0.17, kaizen 2.9, kailash-align 0.x, kailash-pact 0.9). No `kailash[diagnostics]` meta-extra — domain extras (`kaizen[judges]`, `ml[dl]`) are the discovery path.

**Bus factor:** 4 of 7 survive 6-month orchestrator absence (DL, RAG, Alignment, Governance). At-risk: LLM (provider API churn), Agent (Langfuse substitute + cross-SDK TraceEvent fingerprint), Interp (HF major bumps). Mitigation: CODEOWNERS entries per helper, monthly CI smoke tests with `OPENAI_PROD_MODEL` + `OPENAI_FALLBACK_MODEL`, pinned extras.

**MLFP sunset story:** If MLFP retires in 2027, Kailash owns diagnostics outright IF five pre-donation conditions met: no MLFP-specific names, no pedagogical sequencing, no course-private datasets, Foundation copyright header, fresh git history under Foundation authorship. ✓ Achievable with cleanup burden listed above.

**Community extension:** 8th diagnostic is additive — inherit `Diagnostic`, pick protocols, ship in relevant package, add one wiring test, update `specs/diagnostics-catalog.md`. Zero architecture discussion. Zero new package. Third parties may ship their own `foo-diagnostics-for-kailash` PyPI package referencing the core protocols.

## Critical structural wins

1. **Orphan-proof by construction** — every `Diagnostic` subclass requires one `test_<name>_wiring.py` per `rules/facade-manager-detection.md` Rule 2. Mechanical grep gate catches Phase 5.11-class failures before shipping.
2. **Cross-SDK contract frozen at one file** — `schemas/trace-event.v1.json` is the single source of truth. BP-051/052/053 reference it verbatim. Collapses the four existing Rust chain-fingerprint drifts into one reconciliation site.
3. **8th helper is additive** — no more architectural meetings per donation. The extension flow is mechanical.

## Biggest residual risks

1. **Core SDK gains a diagnostics surface it has never had.** Mitigation: protocols + dataclasses only, zero runtime logic, zero optional deps. If it grows logic, the architecture has failed — recovery path is Option C (dedicated `kailash-diagnostics` package).
2. **TraceEvent fingerprint cross-SDK drift (~40% probability over 12 months if unmitigated).** Mitigation: JSON Schema as single source of truth; property-based round-trip test in BOTH SDKs asserts identical fingerprint for identical input; Gate-6 exit criterion.
3. **Plotly blast radius (50MB+ wheel).** Mitigation: `plot_*()` lives on concrete classes only (not `Diagnostic` protocol); gated by `kailash[plot]` extra with loud-fail; `report()` always pure polars + dict. Rust parity uses `plotters-rs` behind `plots` feature flag.

## Decision required

1. **Approve Option E architecture?** (protocols + adapters + engine-extension + GovernanceDiagnostics reject)
2. **Approve 5-6 session commitment** for full landing?
3. **Approve pre-implementation blocker order** (B1–B4 before PR#0)?
4. **Should I file the kailash-rs fingerprint-reconciliation issue NOW** (so B1 can start on the kailash-rs side in parallel with session 1 Python blockers)?

Source deliverables:

- `workspaces/issue-567-mlfp-diagnostics/01-analysis/failure-points.md` (per-helper risk)
- `workspaces/issue-567-mlfp-diagnostics/01-analysis/cross-sdk-parity.md` + `kailash-rs-parity.md`
- `workspaces/issue-567-mlfp-diagnostics/01-analysis/proposal-pattern-architecture.md` (Option E structural)
- `workspaces/issue-567-mlfp-diagnostics/01-analysis/proposal-strategy.md` (licensing + donation model)
- `workspaces/issue-567-mlfp-diagnostics/01-analysis/proposal-longterm-risk.md` (2-year bus-factor)
- `workspaces/issue-567-mlfp-diagnostics/01-analysis/proposal-governance-absorb.md` (PACT capability split)
- `workspaces/issue-567-mlfp-diagnostics/01-analysis/proposal-kaizen-primitives.md` (TraceEvent / JudgeCallable)
