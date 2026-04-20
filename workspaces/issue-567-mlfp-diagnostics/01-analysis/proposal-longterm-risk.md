# Issue #567 — MLFP Diagnostics: 2-Year Long-Term Risk Analysis

**Source**: `terrene-foundation/kailash-py#567` (~7,300 LOC across 7 helpers)
**Horizon**: 2026-04 → 2028-04 (24 months)
**Analyst deliverable**: 2-year scenario-based risk, bus-factor, drift, community, versioning, sunset
**Date**: 2026-04-20

---

## Executive Summary

- **Chosen strategy**: **Option D — Extract 3 primitives (`Diagnostic` protocol + `TraceEvent` schema + `JudgeCallable` protocol) into `kailash` core, adapters land per-package** — with Option A phasing for the six non-blocked helpers.
- **2-year bus-factor verdict**: **4 of 7 helpers survive a 6-month orchestrator absence** (DL, RAG, Alignment, Interpretability). **3 do NOT** without explicit maintenance ownership assigned at merge time (LLM, Agent, Governance — all carry upstream-dep or cross-SDK coupling that atrophies silently).
- **Biggest drift risk**: The `TraceEvent` / audit-chain fingerprint surface. Four Rust impls already drift on `prev_hash` format (per `kailash-rs-parity.md` §5); adding Python `TraceEvent` makes it 5 drift sites. Structural defense: JSON Schema source-of-truth in `specs/diagnostics-protocols.md` + property-based round-trip test in BOTH SDKs.
- **Worst-case sunset**: MLFP course retirement in 2027 leaves orphaned-by-association code. Insurance: pre-donation MUST decouple from any MLFP-specific naming, pedagogical sequencing, or dataset references. After donation, Kailash owns it outright. A `sunset lane` (feature-flagged experimental subpackage) is NOT proposed — it creates the exact orphan pattern `orphan-detection.md` warns against.
- **Recommended sequence** (7 PRs over 12 months): DLDiagnostics → RAGDiagnostics → AlignmentDiagnostics → InterpretabilityDiagnostics → LLMDiagnostics → AgentDiagnostics → GovernanceDiagnostics-redesign. Ordered by risk-weighted landing probability.

---

## 1. Four-Option Projection to 2028-04

### Option A — Direct Upstream (7 PRs, per-helper placement)

**Shape today**: 7 independent PRs against tracking issue #567. Each helper lands in its target package's existing namespace. No shared abstraction.

**2028-04 projection:**

| Dimension                  | Trajectory                                                                                                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LOC growth                 | 7,300 baseline → ~12,000 (+65%). Each helper accretes dialect-specific tweaks (CUDA variant for DL, vLLM variant for Interpretability, OpenAI/Anthropic judge variants for LLM) |
| Bus-factor                 | **2** (DL-alignment-interpretability share torch ownership; RAG isolated; LLM+Agent share kaizen.providers ownership; Governance requires pact-specialist)                      |
| Cross-SDK parity drift     | **HIGH** — 3 helpers in kailash-rs (per BP-051/052/053); no shared schema = one drift per release per SDK = ~12 drift events over 2 years                                       |
| Test flakiness             | Compounding — each helper adds its own CI matrix; 7 helpers × 5 Python versions × 2 OS = 70 job-slots, ~2-3% flake rate per slot = weekly flake-fires                           |
| Community extension PRs/mo | **0.5–1** (each helper has its own public surface; contributors would PR into the sub-package most aligned with their domain, but discoverability is low)                       |

**Verdict**: Fastest to ship. Worst for drift. Maintainability gradient steep after 12 months.

---

### Option B — Extract `Diagnostic` Base Class First, Then Donate Adapters

**Shape today**: New `kailash.diagnostics.base.Diagnostic` abstract class in `kailash` core. Each of the 7 helpers becomes a subclass. Single `report() -> dict`, `plot() -> go.Figure`, context-manager protocol.

**2028-04 projection:**

| Dimension                  | Trajectory                                                                                                                                                        |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LOC growth                 | 7,300 + 400 (base class) → ~10,000 (+37%). Shared base suppresses per-helper accretion                                                                            |
| Bus-factor                 | **3** (base class is the single shared surface; anyone touching a subclass needs to understand the ABC contract; raises onboarding cost but compresses ownership) |
| Cross-SDK parity drift     | MEDIUM — base class contract is specifiable (`Diagnostic.report() -> Dict[str, Any]`); subclass drift still possible but narrower                                 |
| Test flakiness             | Reduced — shared contract tests (e.g. "every Diagnostic subclass MUST return dict with `tenant_id` key") run once; per-subclass tests are smaller                 |
| Community extension PRs/mo | **1–2** — base class is a documented extension point; third-parties build `MyCustomDiagnostic(Diagnostic)` without PRing into Kailash                             |

**Risk**: ABC contract is load-bearing. Changing `Diagnostic.__enter__()` signature in year 2 forces major-bump across every sub-package (ml, kaizen, align, pact all version-bump together). See §5 for the versioning-cliff analysis.

**Verdict**: Cleanest abstraction. Longest up-front cost. ABC rigidity becomes a tax.

---

### Option C — New Cross-Cutting `kailash-diagnostics` Package

**Shape today**: New top-level package `pip install kailash-diagnostics`. All 7 helpers live there. Imports from kaizen/ml/align/pact as needed.

**2028-04 projection:**

| Dimension                  | Trajectory                                                                                                                                                               |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| LOC growth                 | 7,300 + 600 (package scaffolding) → ~11,000 (+50%)                                                                                                                       |
| Bus-factor                 | **1** (package owner = diagnostics-specialist, which does NOT exist today; creates a new specialist role)                                                                |
| Cross-SDK parity drift     | HIGH — the diagnostics package becomes its own evolution vector, unlikely to stay synchronized with the four host packages                                               |
| Test flakiness             | New package = new CI = new flake surface. +15% CI minutes vs baseline                                                                                                    |
| Community extension PRs/mo | **2–3** — cross-cutting packages attract third-party plugins (grafana exporter, langfuse exporter, prometheus exporter); Foundation becomes the plugin-triage bottleneck |

**Risk**: Creates an orphan pattern. If kailash-kaizen evolves its `ObservabilityManager` and `kailash-diagnostics` doesn't follow, agent-diagnostics breaks silently. Cross-package version dependencies (`kailash-diagnostics>=0.5 requires kailash-kaizen>=3.0`) become version-bump arithmetic.

**Verdict**: Worst for drift. Creates a new facade that the framework hot paths don't call. Rejected.

---

### Option D — Extract 3 Primitives (`Diagnostic` protocol + `TraceEvent` + `JudgeCallable`)

**Shape today**: `kailash.diagnostics.protocols` module with three `typing.Protocol` (not ABC) definitions. Each helper lands in its target package and implements the protocol. No inheritance coupling.

**2028-04 projection:**

| Dimension                  | Trajectory                                                                                                                                                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LOC growth                 | 7,300 + 150 (3 Protocol classes, no default implementations) → ~10,500 (+44%). Protocol-vs-ABC saves 250 LOC vs Option B                                                                      |
| Bus-factor                 | **3** (same as Option B, but the Protocol stays duck-typed; a helper can diverge from the Protocol with a typed mypy error rather than a runtime-ABC contract violation — easier remediation) |
| Cross-SDK parity drift     | **LOW** — Protocol corresponds 1:1 to a JSON Schema; schema lives in `specs/diagnostics-protocols.md` as shared source of truth between kailash-py and kailash-rs                             |
| Test flakiness             | Same as Option B                                                                                                                                                                              |
| Community extension PRs/mo | **1–2** — same as Option B; Protocol is self-documenting via `@runtime_checkable` at runtime                                                                                                  |

**Verdict**: **Recommended.** Minimal shared surface (3 Protocols, ~50 LOC each), maximum drift resistance, lowest ABC-rigidity cost, explicit JSON Schema source of truth for cross-SDK. Matches `rules/orphan-detection.md` §1 — Protocols are contracts, not facades, so they don't need production call sites the way `*Manager` classes do.

---

## 2. Bus-Factor Analysis — Can ONE Contributor Maintain?

**Scenario**: Orchestrator (current Claude session) is unavailable for 6 months starting 2026-10. Ranking by upstream-dep-churn risk (worst to best):

### Rank 1 (HIGHEST churn risk): LLMDiagnostics + JudgeCallable

- **Churn sources**: `bert-score` pins transformers (minor version sensitive), `rouge-score` unmaintained-ish (last release 2022), LLM provider API shifts (OpenAI deprecates `gpt-4` → `gpt-4-turbo` → `gpt-4o` → `gpt-4.5` every ~6 months), Delegate routing contract could change in kailash-kaizen
- **Bus-factor**: 0 without explicit ownership. Would break in ~3 months silently as an LLM API deprecates
- **Fallback if provider deprecates**: `.env`-driven model selection already insulates; CI must include `.env.ci` with current+next model names
- **Required insurance**: `kaizen[judges]` extras MUST pin `bert-score>=0.3.13,<1.0` + monthly automated CI run against a judge-smoke-test using OPENAI_PROD_MODEL + OPENAI_FALLBACK_MODEL

### Rank 2: AgentDiagnostics + TraceEvent

- **Churn sources**: `kaizen.providers.cost.CostTracker` microdollar contract (already broke once per journal), `ObservabilityManager` internals, trace export Protocol (if we end up with 3 exporters, each is a churn surface)
- **Bus-factor**: 1 (kaizen-specialist owns the adjacent surface)
- **Fallback if CostTracker changes**: semantic version gate; Agent diagnostics declare `kailash-kaizen>=X.Y,<X+1.0`
- **Required insurance**: contract test asserting `AgentTrace.total_cost_microdollars == CostTracker.total_cost_microdollars` on a real run

### Rank 3: InterpretabilityDiagnostics

- **Churn sources**: HF `transformers` major version bumps (~every 6 months, occasional backwards-incompatible), `sae-lens` optional dep (young library, pre-1.0, API churn expected), model-loading API changes (`AutoModelForCausalLM.from_pretrained` adds/removes kwargs)
- **Bus-factor**: 1 (kaizen-specialist, but interpretability-specific knowledge is rare)
- **Fallback if HF transformers changes API**: pin to a known-good range; ship with `local_files_only=True` default to avoid HF Hub API coupling
- **Required insurance**: `kaizen[interpretability]` extras pin `transformers>=4.40,<5.0`; monthly CI against one local 125M-param model (TinyLlama) to catch API drift

### Rank 4: DLDiagnostics

- **Churn sources**: torch hook semantics (stable since 2.0; low churn), Lightning callback API (stable), Plotly figure schema (very stable)
- **Bus-factor**: **2** (ml-specialist is robust; pytorch-lightning contributor surface is large enough that any refactor gets caught)
- **Fallback**: torch hooks are public API; Lightning has LTS branches
- **Required insurance**: standard Tier 2 test against real MNIST-scale fit; pin torch to a major (`torch>=2.2,<3.0`)

### Rank 5: AlignmentDiagnostics

- **Churn sources**: `trl` API (Apache 2.0, somewhat active but narrow surface), kailash-align hook surface
- **Bus-factor**: **2** (align-specialist + trl community)
- **Fallback if `trl` deprecates**: the closed-form KL divergence and reward-margin math is pure numpy; ship with a numpy-only path and mark the trl-assisted path as optional
- **Required insurance**: numpy-path and trl-path both have Tier 2 tests; the numpy path is the fallback

### Rank 6: RAGDiagnostics

- **Churn sources**: polars (stable, mature 1.0+), scipy (glacial), no provider coupling
- **Bus-factor**: **3** (pure compute, easy onboarding, large community)
- **Fallback**: none needed — no external service deps
- **Required insurance**: standard Tier 2

### Rank 7 (LOWEST churn risk): GovernanceDiagnostics (post-redesign)

- **Churn sources**: only `pact.audit` internals (owned by Foundation, low churn)
- **Bus-factor**: **2** (pact-specialist + Foundation governance team)
- **Fallback**: n/a — Foundation code
- **Required insurance**: cross-SDK fingerprint reconciliation (blocking per kailash-rs-parity.md §5)

**Bus-factor verdict**: 4 of 7 (DL, RAG, Alignment, Governance-redesign) survive 6-month orchestrator absence. 3 of 7 (LLM, Agent, Interpretability) require explicit documented ownership assignment at merge time — otherwise they atrophy silently from upstream churn. Merge-time insurance: `CODEOWNERS` entries, monthly CI smoke tests with current-model + fallback-model, pin ranges in extras.

### Plotly drops Python 3.11 support

Plotly is already a base dep. If 3.11 is dropped in 2027, kailash-ml drops 3.11 in the same release (ecosystem-wide move, not a DL-diagnostic-specific concern). The seven helpers inherit this, they don't amplify it.

---

## 3. Cross-SDK Drift Risk

### Current drift inventory (per kailash-rs-parity.md §5)

Four Rust audit-chain impls already drift on `prev_hash` format:

- `kailash-core::audit_log` — colon-joined string hash input, `""` genesis
- `kailash-enterprise::audit::sqlite` — canonical event bytes + hex prev_hash, `NULL` genesis
- `kailash-pact::audit` — no prev_hash chain at all (only `content_hash()`)
- `eatp::ledger` — bytes prev_hash + content_json, `None` genesis

### 12-month drift probability per new primitive

**`TraceEvent`**: 40% drift probability. Span/Trace exist in both SDKs but with different names and field shapes. Without a shared JSON Schema, adding Python `TraceEvent` creates a fifth canonical form. **Mitigation**: `specs/diagnostics-protocols.md` with JSON Schema, property-based roundtrip test in BOTH SDKs that serializes a Python `TraceEvent` and deserializes in Rust (same fingerprint).

**`JudgeCallable`**: 15% drift probability. Rust has no judge runtime today (per kailash-rs-parity.md §7 — NO-GO). No drift surface exists until kailash-rs builds a judge. When that happens, Python is the reference implementation — drift protection via shared spec file.

**`Diagnostic` protocol**: 20% drift probability. Both SDKs can conform to "has report()/plot()/context-manager" surface; the drift risk is in the report dict shape, not the Protocol signature. **Mitigation**: the shared JSON Schema pins the report() return type's required keys (`tenant_id`, `device`, `timestamp`, `helper_version`).

### Structural defenses (in priority order)

1. **Shared JSON Schema** in `specs/diagnostics-protocols.md` — ONE source of truth across both SDKs. Property-based round-trip test in both SDKs that serializes + deserializes + asserts structural equality. (Highest priority, lowest cost.)
2. **Cross-SDK CI job** that installs both SDKs, emits a `TraceEvent` from Python, reads it in Rust, asserts identical fingerprint. (Second priority.)
3. **Generated code** from the JSON Schema (dataclasses_json or quicktype) — rejected. Codegen toolchains introduce more churn than they prevent.
4. **Pre-commit hook** that blocks edits to `TraceEvent` in one SDK without a same-PR note referencing the sibling SDK. (Lowest priority; enforceable but easy to bypass.)

**Biggest drift risk summarized**: The `TraceEvent` schema, because (a) it's already drifting on the Rust side across 4 audit-chain impls, (b) it's the one primitive with active consumers in BOTH SDKs, and (c) forensic correlation across polyglot deployments literally depends on fingerprint stability per `rules/event-payload-classification.md` MUST Rule 2.

---

## 4. Community Extension Risk

**Assumption**: 2 third-party adapter PRs per quarter × 8 quarters = 16 contributions over 2 years.

### Triage model

**Recommended**: Foundation DOES NOT accept third-party diagnostic adapters into the core packages. The Protocol surface (`Diagnostic`, `TraceEvent`, `JudgeCallable`) is the extension point. Third parties ship their own `pip install kailash-diagnostics-langfuse` / `kailash-diagnostics-grafana` / etc.

**Rationale**:

- Foundation-independence (`rules/independence.md`) — accepting `langfuse` or `grafana` exporters into core creates implicit commercial coupling
- Bus-factor — every accepted adapter adds a maintenance surface the Foundation now owns. 16 adapters × ~800 LOC = 12,800 LOC of surface inherited from volunteers who may not stick around
- `rules/orphan-detection.md` §1 — accepted adapters need framework hot-path call sites. Third-party adapters are by definition invoked only when the third-party user configures them, which makes them fail the "call site in framework" rule

### Acceptable community contributions

- Bug fixes to existing 7 diagnostics
- Performance improvements to existing 7 diagnostics (with benchmarks)
- New metric families to existing diagnostics (e.g., new RAG metric that reuses RAGDiagnostics infrastructure)
- Protocol extensions (new method on `Diagnostic` Protocol), behind a compat-migration issue

### 2-year outcome

- 4 of 16 hypothetical PRs accepted (bug fixes, minor metrics)
- 12 of 16 redirected to "ship as your own package implementing our Protocol"
- Foundation ships a `kailash-diagnostics-adapters-registry.md` page that links community packages that implement the Protocol — community discoverability without maintenance burden

---

## 5. Versioning / Breaking-Change Risk

### Current state

Each helper lives in its target package (`kailash-ml`, `kailash-kaizen`, `kailash-align`, `kailash-pact`). First breaking change to any diagnostic triggers its host package's major bump.

### Experimental / 0.x policy proposal

The Foundation MUST adopt an **experimental subpackage** convention for the first 12 months of each diagnostic:

- Module lives at `kailash_ml.experimental.dl_diagnostics` (not `kailash_ml.engines.dl_diagnostics`) for first 12 months
- `from kailash_ml.experimental import DLDiagnostics` emits a `FutureWarning` on first import: "This API is experimental and may change; graduate to kailash_ml.engines in version X.Y"
- After 12 months in experimental WITHOUT breaking changes, graduate to stable namespace and lock the public surface
- Any breaking change during experimental period is a MINOR bump, not major

### Trade-off

- Experimental lane protects adopters from major-bump churn during the shakedown period
- Experimental lane also creates a graduation cliff — the module moves from `experimental.X` to `Y.X`, every import downstream must change, which is itself a breaking change
- Mitigation: at graduation, leave a `experimental.X` re-export module that emits `DeprecationWarning` for 1 additional version, then delete (per `rules/orphan-detection.md` §3 — removed = deleted, not deprecated forever)

**Recommendation**: ADOPT the experimental namespace convention. File it as `rules/experimental-lane.md` during `/codify` of this workstream.

---

## 6. Worst-Case "Sunset MLFP" Scenario

### Scenario

In 2027, the Terrene Foundation decides to retire MLFP (Machine Learning Fundamentals Program) — either replaced by a newer curriculum, wound down due to instructor departure, or rescoped. What happens to the 7 donated diagnostics?

### What MUST be true at donation time (pre-donation insurance)

1. **No MLFP-specific names in code or docstrings**. No `@mlfp_lesson_42` decorators, no "See Chapter 7" comments, no `mlfp_example_dataset` references
2. **No pedagogical sequencing assumptions**. The diagnostics don't assume the user has seen a preceding lesson. Each helper stands alone with its own docstring
3. **No course-private datasets**. If DL diagnostic examples use a dataset, it's a public dataset (MNIST, CIFAR, WikiText) shipped or fetched under permissive license
4. **Foundation copyright on every file**. Apache 2.0 header with `Copyright (c) 2026 Terrene Foundation` — NOT the course author's personal copyright. This is the legal precondition for continued ownership after course retirement
5. **Separate git history**. Donation PR does NOT import MLFP git history. Fresh commits under Foundation authorship

### If MLFP retires in 2027

- Kailash owns the diagnostics outright (point 4 above). No license ambiguity, no "MLFP course content" rights to negotiate
- Maintenance continues under the target package's existing specialist ownership. No change to the user-facing API
- The diagnostics were never MLFP's in the first place after donation — "MLFP donated them in 2026" becomes a historical footnote in the CHANGELOG, not a living dependency
- `sunset lane` is NOT proposed. Creating a feature-flagged "this may be removed" namespace is exactly the facade-orphan pattern `rules/orphan-detection.md` warns against — users don't migrate off a deprecated namespace until they're forced to, and the Foundation ends up maintaining two copies

### What IS proposed at donation time

- Each PR body references the pre-donation insurance checklist (§6 above) and the reviewer verifies it
- The donation PR is not merged until all 5 conditions are verified

---

## 7. Sequenced Risk-Gate Proposal (Chosen Strategy: Option D)

### Landing order (risk-ascending)

| Gate | Helper                         | Target                | Exit Criteria                                                                                                                        | Cumulative risk |
| ---- | ------------------------------ | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------- |
| 1    | DLDiagnostics                  | kailash-ml 0.16.0     | 3-tier tests green on CPU + 1 GPU; medical-metaphor grep regression test green; Tier 2 test via facade; `DeviceReport` in report()   | Low             |
| 2    | RAGDiagnostics                 | kailash-ml 0.17.0     | 3-tier green; polars streaming mode tested at 100k query scale; cross-SDK parity BP-053 issue filed and acknowledged                 | Low             |
| 3    | AlignmentDiagnostics           | kailash-align x.y.z   | 3-tier green; trl-path and numpy-path both have Tier 2 tests; kailash-align trainer hook surface version-gated                       | Low-Med         |
| 4    | InterpretabilityDiagnostics    | kailash-kaizen 2.9.x  | 3-tier green; `[interpretability]` extras pin transformers<5; local-only model loading default; monthly TinyLlama CI smoke scheduled | Medium          |
| 5    | LLMDiagnostics + Judge         | kailash-kaizen 2.8.x  | 3-tier green; Delegate routing verified; structured judgment signature (not regex); CostTracker microdollar integration with test    | Medium-High     |
| 6    | AgentDiagnostics               | kailash-kaizen 2.10.x | 3-tier green; Langfuse stripped from pyproject; TraceEvent JSON Schema landed in specs/; cross-SDK property-based round-trip passes  | High            |
| 7    | GovernanceDiagnostics-redesign | PACT extension        | Cross-SDK fingerprint reconciliation complete; PACT engine methods (not new facade); redesign PR separate from #567                  | High            |

### Explicit exit criteria per gate

**Gate 1 (DLDiagnostics)**:

- Tier 1 unit tests for gradient-flow, activation-saturation, LR-range separately
- Tier 2 MNIST-scale fit test on CPU + one GPU (CUDA 12.x) — asserts `report()["dead_neurons"]` non-empty, `report()["device"]` matches `DeviceReport` contract
- Medical-metaphor grep regression green across all 4 packages
- 2 weeks in main with zero issues before Gate 2 starts

**Gate 2 (RAGDiagnostics)**:

- 3-tier green
- Scale test: 100k queries × 1k docs each via polars LazyFrame — asserts peak memory <4GB
- kailash-rs BP-053 issue filed, linked in PR body, acknowledged by RS maintainer

**Gate 3 (AlignmentDiagnostics)**:

- 3-tier green
- Tier 2 against real 2-step SFT run on a 125M-param model
- Both trl-path and numpy-path have tests; numpy path is the fallback if trl deprecates
- kailash-align hook surface version-gated (`kailash-align>=X.Y`)

**Gate 4 (InterpretabilityDiagnostics)**:

- 3-tier green
- `[interpretability]` extras pinned `transformers>=4.40,<5.0`
- Default `local_files_only=True`; no HF Hub network calls in test runs
- Monthly scheduled CI job runs TinyLlama smoke test against latest transformers patch

**Gate 5 (LLMDiagnostics + Judge)**:

- 3-tier green
- Delegate routing verified by test that mocks the raw OpenAI endpoint and asserts Delegate path is used
- Position-swap bias mitigation implemented via structured signature, NOT regex (regression test with DSPy-style signature)
- CostTracker microdollar integration test: `tracker.total_cost_microdollars == N` after N judge calls at known token costs
- `JudgeBudgetExhausted` typed exception on budget cap, not silent partial result

**Gate 6 (AgentDiagnostics)**:

- Langfuse NOT in pyproject.toml (independence audit grep test)
- `TraceEvent` JSON Schema landed in `specs/diagnostics-protocols.md`
- Cross-SDK property-based round-trip: Python emits `TraceEvent`, Rust deserializes, fingerprint matches
- CostTracker integration assertion (same as Gate 5)
- Tool-usage label cardinality bounded (top-N bucketing)
- 2 weeks in main + post-release reviewer sweep per `rules/agents.md` "After release" gate

**Gate 7 (GovernanceDiagnostics-redesign)**:

- Cross-SDK fingerprint reconciliation issue filed in kailash-rs and ACCEPTED (prereq per kailash-rs-parity.md §5)
- Functionality absorbed as methods on `GovernanceEngine`, NOT a new facade class
- No "negative drills" helper in production code (belongs in `pact.governance.testing`)
- Close #567's GovernanceDiagnostics line item with reference to the new PACT-engine extension ticket (not silently dropped per `rules/git.md` Issue Closure Discipline)

### Total timeline estimate

7 gates × ~1 autonomous execution cycle per gate = **~7 sessions** in the aggressive case. With post-release 2-week soak between gates: 4 months calendar time for Gates 1-5, then 6-8 weeks for Gate 6 (cross-SDK work is human-authority gated), then 8-12 weeks for Gate 7 (prereq fingerprint reconciliation). **Total: 8-12 months calendar**.

---

## 8. Success Criteria (2028-04 check-back)

- [ ] All 6 accepted helpers in stable namespace (not `.experimental.`) with zero security CVEs reported
- [ ] Bus-factor ≥2 on every helper; CODEOWNERS entries per helper; monthly smoke-test CI on LLM+Interpretability helpers shows zero silent-API-drift breakage
- [ ] Cross-SDK `TraceEvent` fingerprint round-trip test passing in both repos for ≥18 months
- [ ] Community packages implementing `Diagnostic` Protocol exist and are linked from `docs/diagnostics-adapters-registry.md`; Foundation has NOT absorbed any of them into core
- [ ] GovernanceDiagnostics redesign merged; no "diagnostics" facade on PACT; functionality lives on `GovernanceEngine`
- [ ] Zero `NotImplementedError` deferrals remain from 2026 donation; all public API stable per `rules/orphan-detection.md` §4a

---

## 9. Reference Rules Applied

- `rules/autonomous-execution.md` — 10x multiplier, per-session capacity budget (§1 sharding motivates 7 sequential PRs, not mega-PR)
- `rules/agents.md` — parallel-worktree ownership (if Gates 4+5 run in parallel, both touch kaizen pyproject; MUST assign single version owner)
- `rules/orphan-detection.md` §1 (facades need production call sites), §3 (deleted not deprecated), §4a (stub un-deferral sweep), §6 (`__all__` contract)
- `rules/facade-manager-detection.md` (rejects GovernanceDiagnostics as a new facade)
- `rules/independence.md` (Langfuse strip, community adapter policy)
- `rules/event-payload-classification.md` MUST Rule 2 (cross-SDK fingerprint stability)
- `rules/tenant-isolation.md` MUST Rule 4 (agent-diagnostics metric label cardinality)
- `rules/specs-authority.md` MUST Rule 5b (full sibling spec sweep after spec edits)
- `rules/zero-tolerance.md` Rule 2 (reject fake implementations — the Phase 5.11 orphan pattern applies directly here)
