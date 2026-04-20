# Issue #567 — At-The-Root Architecture for MLFP Diagnostics

**Scope**: Architectural proposal for the ~7,300 LOC MLFP diagnostics upstream.
Not per-helper disposition (see `failure-points.md`) — this document asks: what
shape MUST the Kailash platform accept these helpers into, such that the 8th,
9th, and 10th helper donated in 2027 is additive, not another architectural
discussion?

**Date**: 2026-04-20
**Status**: Draft for human decision gate

---

## 1. Pattern Extraction — The Common Shape Is Richer Than The Issue Body States

The issue itself lists: "context manager, polars DataFrames, `plot_*()` →
`go.Figure`, `report()` → dict, `run_id`". A structural read of the seven
helpers against existing Kailash rules and existing primitives surfaces
**nine** shared invariants, not five:

| #   | Invariant                         | Helpers that need it                                    | Existing Kailash primitive (if any)                                            |
| --- | --------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 1   | Context-manager scope             | ALL 7                                                   | Python `contextlib` — generic                                                  |
| 2   | `run_id` correlation              | ALL 7                                                   | `kaizen.observability.TracingManager` span IDs; `ml-tracking.md` run IDs       |
| 3   | `polars.DataFrame` as tabular IO  | ALL 7 (reports), 4 of 7 (inputs — RAG, LLM, Agent, Gov) | `kailash_ml.metrics` + `kailash_ml.engines.*` already polars-native            |
| 4   | `report() → dict` + frozen schema | ALL 7                                                   | `kailash_ml._result.TrainingResult` + `kailash_ml._results.*` frozen dataclass |
| 5   | `plot_*() → go.Figure`            | 6 of 7 (Gov has no plot)                                | `kailash_ml.engines.model_visualizer` already plotly                           |
| 6   | Time-window scoping               | Agent, Gov (time-bounded audit queries)                 | None; generally ad-hoc                                                         |
| 7   | Budget-gating                     | LLM (judge), Agent (cost), Gov (budget consumption)     | `kaizen.providers.cost.CostTracker` (microdollars, tenant-scoped)              |
| 8   | Trust-lineage attribution         | Gov, Agent, LLM (judge verdicts need provenance)        | `kailash.trust.pact.audit` chain (SHA-256 + `prev_hash`); `eatp.ledger`        |
| 9   | Hierarchical aggregation          | DL (per-layer), RAG (per-query), Agent (per-span)       | None; each helper hand-rolls                                                   |

**Finding**: The "five-invariant" framing in the issue body under-counts the
contract by four. Budget-gating (invariant 7) and trust-lineage (invariant 8)
are the two that make or break the "at-the-root" decision — they are where the
7 helpers overlap with PACT, Kaizen-observability, and `kailash.trust` and
therefore where the orphan-detection / facade-manager-detection rules
(`rules/orphan-detection.md` §1, `rules/facade-manager-detection.md`) will
either catch real architectural drift or miss it entirely if routed wrong.

**Invariant 8 in particular** ties to
`rules/event-payload-classification.md` MUST Rule 2 — the SHA-256 hash shape
for record_id fingerprints is a cross-SDK stability contract. Any diagnostic
that emits fingerprints MUST share the canonical hash format across py/rs.

---

## 2. Option Comparison

Four options (A / B / C / D) plus a synthesis (E). The evaluation axes are:

- **Blast radius** — how much surface does this introduce on day 1?
- **Orphan risk** — how many `*Engine` / `*Manager` / `*Store` shapes land that
  the framework hot path must actually call (`rules/orphan-detection.md` §1)?
- **Cross-SDK parity cost** — what is the BP-051/052/053 spec burden, and does
  every abstraction carry a Rust equivalent?
- **Community extension story** — when the 8th diagnostic arrives, is the
  contract additive or does the door need to be reopened?
- **Maintenance burden** — how many sibling-spec sweeps does a future edit
  trigger (`rules/specs-authority.md` 5b)?
- **Framework-first fit** — does the surface respect the domain→framework
  bindings in `rules/framework-first.md`?

### Option A — Accept per-issue, no shared abstraction (7 classes in their domain packages)

| Axis                  | Assessment                                                                     |
| --------------------- | ------------------------------------------------------------------------------ |
| Blast radius          | Lowest — each helper ships where `failure-points.md` says it goes              |
| Orphan risk           | HIGH — 7 `*Diagnostics` facades × 4 packages; no shared wiring test discipline |
| Cross-SDK parity cost | 3 independent BPs, each re-inventing the fingerprint contract                  |
| Community extension   | ZERO — every future helper is another architectural discussion                 |
| Maintenance burden    | 7 independent spec files; 7 sibling-sweep domains                              |
| Framework-first fit   | Partial — Gov still violates `rules/pact-governance.md` MUST #1                |

**Verdict**: Ships fast, accumulates architectural debt at exactly the rate
Phase 5.11 did. BLOCKED by `rules/autonomous-execution.md` — autonomous
execution capacity is high enough to do this right.

### Option B — `Diagnostic` abstract base class in a shared location

Concrete location choices:

- `kailash.diagnostics` — core SDK (but core SDK currently carries zero
  diagnostic surface, and `rules/independence.md` says we design for SDK users
  at large, not for MLFP's convenience)
- `kailash-ml.diagnostics` — adds load-bearing logic to kailash-ml for all 7
  helpers, including those that have zero ML semantics (Gov, Agent)
- `kaizen.diagnostics` — same problem inverted (DL/RAG/Alignment are not Kaizen)

| Axis                  | Assessment                                                                      |
| --------------------- | ------------------------------------------------------------------------------- |
| Blast radius          | Medium — shared ABC, 7 concrete subclasses, one new symbol surface              |
| Orphan risk           | Medium — ABC with one wiring-test template catches 7 helpers at once            |
| Cross-SDK parity cost | 3 BPs share a protocol definition — saves ~30% spec effort                      |
| Community extension   | GOOD — 8th helper = subclass `Diagnostic`                                       |
| Maintenance burden    | 1 ABC file + 7 concretes; one sibling sweep per edit (`specs/diagnostics-*.md`) |
| Framework-first fit   | Good IF the ABC lives somewhere the 7 domain helpers can all inherit from       |

**Location problem**: There is no existing shared home. Putting the ABC in
core SDK (`src/kailash/diagnostics/`) is the only option that doesn't violate
`rules/framework-first.md` domain binding by forcing (e.g.) kaizen to import
from kailash-ml. This is plausible but needs justification — core SDK currently
has no diagnostic surface.

### Option C — New cross-cutting `kailash-diagnostics` package

Like Trust, Execution, Governance — diagnostics as a first-class plane.

| Axis                  | Assessment                                                                              |
| --------------------- | --------------------------------------------------------------------------------------- |
| Blast radius          | HIGHEST — new package, new pyproject, new CHANGELOG, new CI matrix, new release cadence |
| Orphan risk           | Low — dedicated package forces wiring discipline from day 1                             |
| Cross-SDK parity cost | Full Rust parity crate (`crates/kailash-diagnostics`) required for EATP D6              |
| Community extension   | EXCELLENT — additive to a known surface                                                 |
| Maintenance burden    | One spec domain (`specs/diagnostics-*.md`)                                              |
| Framework-first fit   | New domain in the framework table — requires `rules/framework-first.md` edit            |

**Problem**: The 7 helpers are a mix of domain-specific probes that MUST stay
with their domain (DL with torch/lightning, Alignment with align's trainer
hooks, Interp with HF transformers). Pulling the compute into a central
package breaks those domain tie-ins. The package would either (a) be a thin
protocol/ABC surface only — which is Option B with a separate wheel — or (b)
become a dumping ground that reaches back into every other framework.
`kailash-diagnostics.DLDiagnostics` needing `torch`, `lightning`, AND `kaizen`
is the exact anti-pattern that bloated kaizen's Cargo.toml in `kailash-rs`
(see parity doc §1.1 rationale for new crate `kailash-rag-diagnostics` rather
than kaizen bloat).

### Option D — 3 primitives + domain adapters (REFRAMING)

Recognize the 7 helpers as **3 cross-cutting primitives** + **domain adapters**:

1. **`JudgeCallable` protocol** (Kaizen) — one primitive, used by LLMDiagnostics
   - any future graded-evaluation helper
2. **`TraceEvent` schema** (Kaizen observability) — one primitive, used by
   AgentDiagnostics + any future span-capture helper
3. **`Diagnostic` protocol** (cross-cutting, shared) — one primitive, used by
   all 7 helpers

Everything else (DLDiagnostics' torch hooks, RAGDiagnostics' metric math,
InterpretabilityDiagnostics' logit lens, AlignmentDiagnostics' KL math,
GovernanceDiagnostics' chain-read) is **domain-specific code** that happens to
implement the `Diagnostic` protocol from its own domain package.

| Axis                  | Assessment                                                                       |
| --------------------- | -------------------------------------------------------------------------------- |
| Blast radius          | Medium — 3 small protocol/schema definitions + per-domain implementations        |
| Orphan risk           | Lowest — 3 primitives each have ONE cross-SDK owner; domain adapters land in     |
|                       | their domain package with local wiring discipline                                |
| Cross-SDK parity cost | 3 protocol defs share schema; only primitives need cross-SDK parity (BP-051/052) |
| Community extension   | EXCELLENT — 8th helper picks the right primitive and implements it               |
| Maintenance burden    | 3 primitive specs + 4 domain specs; sibling sweeps stay bounded                  |
| Framework-first fit   | BEST — each helper lives under the framework that owns its domain                |

**This is the option that respects `rules/framework-first.md` AND the
existing Kailash architecture AND MLFP's intent.**

### Option E — Synthesis (recommended)

**Option D as the architecture, with Option B's `Diagnostic` protocol living
in core SDK (`src/kailash/diagnostics/protocols.py`) so every framework can
inherit without creating a domain-awkward home.**

Concretely:

- **Core SDK** (`src/kailash/diagnostics/`) — protocols only, zero domain logic:
  - `Diagnostic` protocol (context manager + `run_id` + `report()` + optional
    `plot()` + sha256 fingerprint on `run_id` matching
    `rules/event-payload-classification.md` MUST Rule 2)
  - `TraceEvent` dataclass (cross-SDK stable schema)
  - `JudgeCallable` protocol (input/output typed signature)
  - `DiagnosticReport` frozen dataclass base (mirrors `kailash_ml._result`
    convention)
- **Kaizen** — `JudgeCallable` concrete implementations (`kaizen.judges.*`),
  `TraceEvent` emission from `kaizen.observability.TracingManager` (extends
  existing `Span`/`Trace` — NO parallel hierarchy per
  `rules/facade-manager-detection.md`), LLM-specific diagnostics
  (`InterpretabilityDiagnostics`, `AgentDiagnostics`)
- **ML** — ML-specific diagnostics (`DLDiagnostics`, `RAGDiagnostics`) in
  `kailash_ml.diagnostics.*` submodule
- **Align** — `AlignmentDiagnostics` as a `Diagnostic` subclass in
  `kailash_align.diagnostics`
- **PACT** — Governance chain-inspection methods absorbed onto
  `GovernanceEngine` directly (per `failure-points.md` §1.7 reject-for-redesign);
  NO `GovernanceDiagnostics` facade

---

## 3. Recommended Option — **E (Synthesis: core-SDK protocols + domain adapters + Kaizen primitives)**

### 3.1 Three architectural wins

1. **Orphan-proof by construction.** Every `Diagnostic` subclass has exactly
   one wiring-test template (`tests/integration/test_<name>_wiring.py`) per
   `rules/facade-manager-detection.md` Rule 2. The core protocol file defines
   the contract; per-framework `/redteam` enumerates subclasses and fails the
   gate if any lack a wiring test. This converts the Phase 5.11 orphan class
   into a mechanical grep rather than a judgment call.

2. **Cross-SDK contract is frozen at one file.** `src/kailash/diagnostics/
protocols.py` owns the `TraceEvent` JSON schema, the `JudgeCallable`
   signature, and the fingerprint-SHA256 contract. Rust mirrors via BP-051
   reference the same schema verbatim. A future canonicalization dispute
   (parity doc §5 flags four existing fingerprint drifts in the Rust tree) has
   exactly one reconciliation site, not seven.

3. **Community 8th-helper is additive, not architectural.** A future donation —
   say, "SafetyEvalDiagnostics" from a partner course — inherits
   `Diagnostic`, picks which of the 3 primitives (`JudgeCallable`,
   `TraceEvent`, or none) it consumes, ships in a domain package, and adds
   exactly one wiring test. No `rules/framework-first.md` edit, no new
   package, no new spec domain — just an additional concrete class under an
   existing protocol.

### 3.2 Two architectural risks

1. **Core SDK gains a diagnostic surface it has never had.** The only
   precedent for a protocol-only submodule in core SDK is
   `kailash.types` / `kailash.trust` — both are cross-cutting standards
   surfaces. Adding `kailash.diagnostics` is a new domain in the core, and
   `specs/_index.md` will need a new category. Mitigation: keep the module
   strictly protocols + dataclasses; zero runtime logic; zero optional deps.
   If it grows logic, it has failed and we move the package split to Option C.

2. **Plotly dependency blast radius (Invariant 5).** `plotly` is a ~50MB wheel
   with JS assets. Evidence-based recommendation: **`Diagnostic.plot()` is
   optional, gated by a `[plot]` extra, with LOUD failure on missing import
   per `rules/dependencies.md` § "Optional Extras with Loud Failure"**.
   Default return: `report()` → polars + JSON; callers opt into plotly only
   when they render. This preserves pip-install-kailash weight. The `plot()`
   method lives on each concrete subclass (not on the ABC) so non-plotting
   diagnostics (Governance chain-verification) don't inherit the import
   burden. Rust parity: `plotters-rs` gated behind a `plots` feature flag per
   `kailash-rs-parity.md` §4.

---

## 4. Cross-SDK Contract Definitions (Text-Book Specification)

These contracts MUST land in `src/kailash/diagnostics/protocols.py` and MUST
be mirrored 1:1 in `crates/kailash-core/src/diagnostics.rs` (new module) with
identical JSON serialization.

### 4.1 `Diagnostic` protocol

```python
# src/kailash/diagnostics/protocols.py
from __future__ import annotations
from typing import Protocol, Optional, runtime_checkable
import polars as pl

@runtime_checkable
class Diagnostic(Protocol):
    """Cross-domain diagnostic contract.

    Implementations MUST:
    - Be usable as a context manager (`__enter__` / `__exit__`).
    - Carry a `run_id` attribute (correlation ID; SHA-256-hexed when the
      diagnostic scope is opened inside a `tenant_id`-classified context per
      `rules/event-payload-classification.md` MUST Rule 2).
    - Provide `report()` returning a `DiagnosticReport` (frozen dataclass;
      `.to_dict()` emits the cross-SDK JSON schema).
    - Optionally provide `plot_<name>()` methods returning `plotly.graph_objects.Figure`;
      `plot_*()` methods MUST raise `DiagnosticPlotUnavailable` with the
      `kailash[plot]` install instruction when plotly is not installed
      (loud-fail per `rules/dependencies.md`).

    Implementations MUST NOT:
    - Emit any log line at WARN+ containing raw classified field names
      (`rules/observability.md` Rule 8).
    - Perform network I/O that bypasses `kaizen.providers.cost.CostTracker`
      (`rules/framework-first.md` — every outbound LLM call through Delegate).
    """
    run_id: str

    def __enter__(self) -> "Diagnostic": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> Optional[bool]: ...
    def report(self) -> "DiagnosticReport": ...
```

### 4.2 `TraceEvent` schema (cross-SDK stable JSON)

```json
{
  "$schema": "https://terrene.foundation/schemas/kailash/diagnostics/trace-event/v1",
  "type": "object",
  "required": ["trace_id", "span_id", "event_type", "timestamp", "run_id"],
  "properties": {
    "trace_id": { "type": "string", "pattern": "^[0-9a-f]{32}$" },
    "span_id": { "type": "string", "pattern": "^[0-9a-f]{16}$" },
    "parent_span_id": {
      "type": ["string", "null"],
      "pattern": "^[0-9a-f]{16}$"
    },
    "event_type": {
      "type": "string",
      "enum": ["tool_call", "llm_call", "tool_result", "llm_result", "error"]
    },
    "timestamp": { "type": "string", "format": "date-time" },
    "run_id": { "type": "string" },
    "tool_name": { "type": ["string", "null"] },
    "duration_ms": { "type": ["number", "null"] },
    "cost_microdollars": { "type": ["integer", "null"] },
    "tenant_id_fingerprint": {
      "type": ["string", "null"],
      "pattern": "^sha256:[0-9a-f]{8}$",
      "description": "sha256:<first 8 hex chars of tenant_id hash> per rules/event-payload-classification.md MUST Rule 2"
    },
    "attributes": { "type": "object" }
  }
}
```

**Cross-SDK fingerprint contract** (critical): any field ending in `_fingerprint`
in `TraceEvent`, `DiagnosticReport`, or any `Diagnostic` subclass MUST follow:
`sha256:<first 8 hex chars of SHA-256(utf-8-bytes) of raw value>`. This is the
SAME contract as `dataflow.classification.event_payload.format_record_id_for_event`
and MUST match `crates/kailash-core/src/audit_log.rs` (per parity doc §5 —
reconcile the four existing chain impls in the same BP).

### 4.3 `JudgeCallable` protocol

```python
@runtime_checkable
class JudgeCallable(Protocol):
    """LLM-as-judge contract.

    Every JudgeCallable MUST:
    - Be implemented as a `kaizen_agents.Delegate`-wrapped primitive
      (`rules/framework-first.md` — no raw `openai.chat.completions.create`).
    - Use a structured Signature with `OutputField(description="verdict")`
      (no regex-match on free-text per `rules/agent-reasoning.md` MUST Rule 3).
    - Share one `CostTracker` instance (microdollars) across all N calls in a
      single judge invocation (tenant-scoped per `rules/tenant-isolation.md`).
    - Raise `JudgeBudgetExhausted` (typed) on `budget_cap` hit, never a partial
      success.
    """
    async def judge(
        self,
        *,
        candidate: str,
        reference: str | None,
        context: "JudgeContext",
    ) -> "JudgeVerdict": ...

@dataclass(frozen=True)
class JudgeVerdict:
    verdict: str          # structured value from Signature, not free text
    score: float          # [0.0, 1.0]
    reasoning: str        # human-readable
    cost_microdollars: int
    run_id: str
```

Rust parity lives at `crates/kailash-kaizen/src/judges/mod.rs` as a trait with
the same JSON shape on the wire; the Python/Rust contract is the JSON, not the
trait surface.

---

## 5. Plotting Layer — Evidence-Based Decision

**Decision**: pure polars return from `report()`; plotly gated behind
`kailash[plot]` extra with loud-failure at call site.

**Evidence**:

1. `plotly>=5.18` is already a kailash-ml base dep — but kailash-ml is a
   sub-package users opt into via `pip install kailash-ml`. Core SDK
   (`pip install kailash`) does NOT carry plotly, and adding it would break
   the 50-user-kaizen-only baseline.
2. `rules/dependencies.md` § "Optional Extras with Loud Failure" mandates the
   loud-fail-with-install-instruction pattern; `Diagnostic.plot()` is a
   textbook case.
3. `rules/observability.md` — diagnostic output primary form is structured
   data (polars DataFrame + dict). Plots are presentation, not measurement.
4. Rust parity doc §4 already recommends `plotters-rs` behind a `plots`
   feature flag for exactly this blast-radius reason.

**Implementation pattern** (lives on each concrete, not ABC):

```python
# kailash_ml/diagnostics/dl_diagnostics.py
class DLDiagnostics:
    run_id: str

    def report(self) -> DLDiagnosticReport:
        """Always returns polars + dict; zero plotly import."""
        ...

    def plot_gradient_flow(self) -> "go.Figure":
        try:
            import plotly.graph_objects as go
        except ImportError as e:
            raise DiagnosticPlotUnavailable(
                "DLDiagnostics.plot_gradient_flow requires plotly — "
                "install via: pip install kailash-ml[plot]"
            ) from e
        df = self._gradient_flow_frame()  # polars, always available
        return _render_flow(df)
```

---

## 6. Extension Interface — 8th/9th/10th Helper Flow

When (not if) a future course upstreams e.g. `SafetyEvalDiagnostics`:

1. Author inherits `kailash.diagnostics.Diagnostic` protocol.
2. Author picks primitives: needs `JudgeCallable`? Import from
   `kaizen.judges`. Needs `TraceEvent`? Use `kaizen.observability.TracingManager`.
3. Author ships in whichever domain package owns the semantics (likely
   `kaizen.safety.*` for safety-evals, or `kailash_align.diagnostics` if it's
   alignment-stage).
4. Author lands ONE wiring test at `tests/integration/test_safetyeval_
diagnostics_wiring.py` proving `Diagnostic.__enter__` → real infra →
   `Diagnostic.report()` produces the schema + externally-observable effect.
5. Author updates `specs/diagnostics-catalog.md` (new spec, see §7) with a
   one-line entry.
6. DONE — no `rules/framework-first.md` edit, no new package, no new cross-SDK
   BP (the 3 primitives already have Rust parity), no architecture discussion.

This is the "additive extension hygiene" the ultrathink brief asks for.

---

## 7. PR Sequencing — Autonomous Execution Cycles

Constraint from `rules/agents.md` § "Parallel-Worktree Package Ownership
Coordination": PRs touching the same sub-package's `pyproject.toml [project.
optional-dependencies]` or `__init__.py __all__` MUST sequence or designate a
single version owner. Constraint from `rules/autonomous-execution.md`: ≤500
LOC load-bearing + ≤10 invariants per shard.

### PR sequence (8 PRs, ~5-6 autonomous sessions)

| #   | Title                                                       | Package        | Depends on | Parallelizable with                                 | Session budget        |
| --- | ----------------------------------------------------------- | -------------- | ---------- | --------------------------------------------------- | --------------------- |
| 0   | `kailash.diagnostics` protocols + `TraceEvent` JSON schema  | kailash (core) | —          | NONE (foundation)                                   | 1 session             |
| 1   | DLDiagnostics (kailash_ml.diagnostics.dl)                   | kailash-ml     | PR#0       | PR#2, PR#6 (different pkgs)                         | 1 session             |
| 2   | RAGDiagnostics (kailash_ml.diagnostics.rag)                 | kailash-ml     | PR#0, PR#1 | PR#3, PR#6 (serializes with PR#1 on ml pyproject)   | merges into session 2 |
| 3   | LLMDiagnostics + JudgeCallable impls (kaizen.judges.\*)     | kailash-kaizen | PR#0       | PR#1/PR#2, PR#6                                     | 1 session             |
| 4   | InterpretabilityDiagnostics (kaizen.interpretability)       | kailash-kaizen | PR#0, PR#3 | PR#1/PR#2, PR#6; seq with PR#3 on kaizen pyproject  | merges into session 3 |
| 5   | AgentDiagnostics (kaizen.observability submodule extend)    | kailash-kaizen | PR#0, PR#3 | seq with PR#3/PR#4 on kaizen pyproject (same owner) | merges into session 3 |
| 6   | AlignmentDiagnostics (kailash_align.diagnostics)            | kailash-align  | PR#0       | PR#1/PR#2/PR#3 (different pkgs)                     | 1 session             |
| 7   | GovernanceEngine chain-verify + snapshot methods (REDESIGN) | kailash-pact   | PR#0       | Everything (different pkg)                          | 1 session             |

### Parallelization rationale

- **PR#0 BLOCKS all 7** — it lands the `Diagnostic` protocol and `TraceEvent`
  schema everyone inherits.
- **PR#1 and PR#2 serialize** — both touch `packages/kailash-ml/pyproject.toml
[project.optional-dependencies]` and `packages/kailash-ml/src/kailash_ml/
__init__.py` `__all__` (per `rules/orphan-detection.md` §6 eager-import
  discipline). ONE version owner per the parallel-worktree rule; PR#1 agent
  owns 0.18.0 bump, PR#2 appends under the same version as a follow-up commit.
- **PR#3, PR#4, PR#5 serialize** — same rule, one kailash-kaizen version owner
  across the three (2.9.0). The three can be developed in separate worktrees
  but MUST coordinate the kaizen `pyproject.toml` + `__init__.py` owner.
- **PR#6 and PR#7 are independent packages** — parallelize freely with each
  other and with the ml/kaizen tracks.
- **Cross-SDK BP-051/052/053** — file as sibling issues in kailash-rs under a
  single cross-SDK umbrella; the Rust primitives track the Python PR#0.

### Worktree-isolation mandate (per `rules/agents.md` MUST Worktree Isolation)

PR#0 → PR#1/PR#3/PR#6/PR#7 four-way parallel in four separate worktrees.
Version owners: PR#0 orchestrator (no bumps, core SDK release is a separate
gate), PR#1 owns kailash-ml 0.18.0, PR#3 owns kailash-kaizen 2.9.0, PR#6 owns
kailash-align next-minor, PR#7 owns kailash-pact 0.9.0. Each worktree prompt
MUST include relative paths only (per `rules/agents.md` MUST Rule 2) and
incremental commit discipline (MUST Rule 3).

### Spec updates (per `rules/specs-authority.md` MUST Rule 5b full-sibling sweep)

- NEW `specs/diagnostics-protocols.md` (core, introduced in PR#0)
- NEW `specs/diagnostics-catalog.md` (catalog of concrete diagnostics, touched
  by every PR#1-PR#6)
- Each PR triggers full sibling sweep of its domain specs (`specs/ml-*.md`,
  `specs/kaizen-*.md`, `specs/alignment-*.md`, `specs/pact-*.md`)

---

## 8. Summary

**Pick Option E.** Core-SDK protocols (`kailash.diagnostics.*` — Diagnostic,
TraceEvent, JudgeCallable) + domain-owned concretes + Kaizen-hosted primitives
(Judge implementations, TraceEvent emitters) + PACT engine methods (Governance
chain-verify absorbed into `GovernanceEngine`, no diagnostics facade). Plotting
is an optional `[plot]` extra with loud-failure. Fingerprint contract is
SHA-256-8-hex matching `rules/event-payload-classification.md` MUST Rule 2.

**Three wins**: orphan-proof by construction (every Diagnostic has a
wiring-test template), cross-SDK contract frozen at one file, 8th helper is
additive.

**Two risks**: core SDK gains a new protocol surface (mitigation: protocols
only, zero logic, loud-fail if it grows); plotly blast radius (mitigation:
`[plot]` extra, loud-fail, per-concrete method not on ABC).

**PR sequencing**: 8 PRs, PR#0 is the foundation blocker, then PR#1/3/6/7
parallelize via worktree isolation with designated version owners, PR#2/4/5
append sequentially under the same kailash-ml / kailash-kaizen owners. Total
autonomous execution: ~5-6 sessions (10x multiplier applied per
`rules/autonomous-execution.md`).
