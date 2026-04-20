# Issue #567 — MLFP Diagnostics Upstream: Open-Source Strategy

**Agent**: open-source-strategist
**Date**: 2026-04-20
**Input files**: `failure-points.md`, `cross-sdk-parity.md`, `proposal-pattern-architecture.md`
**MLFP judges source**: fetched and audited live from `terrene-foundation/mlfp@main`

---

## 1. Donation vs Partnership — Governance Model

### The Question

MLFP and Kailash are both Terrene Foundation projects. Does "Foundation upstreams its own course material" require the same arm's-length treatment as a commercial vendor contribution?

### Answer: Yes, structurally identical — and that is the correct outcome

`rules/terrene-naming.md` § "Foundation Independence" is unambiguous:

> "No contributor has exclusive rights, special access, or structural advantage. Never describe any commercial entity as having a 'partnership' or 'relationship' with the Foundation — contributors operate under a uniform contributor framework."

The constitution's anti-capture clause applies to ALL contributors, including other Foundation projects. The fact that MLFP is also Foundation-owned changes the **IP ownership question** (both are already Foundation IP, so no CLA is needed — see §2) but does NOT change the **governance question**: the SDK must be designed for SDK users at large, not for MLFP's convenience.

### The Two Models

**Donation model (recommended):**
MLFP transfers 7,300 LOC as a one-time contribution. The code is cleaned up per the checklist in §2, merged via PR, and Kailash owns maintenance thereafter. MLFP consumes Kailash as a downstream user — the same relationship any other course or product has.

**Partnership model (structurally blocked):**
MLFP becomes an "ongoing upstream source" with structural cross-reference from both sides. This creates exactly the asymmetric relationship the constitution forbids: MLFP would have implicit influence over SDK design decisions because its helpers are co-maintained. A future contributor who is not affiliated with MLFP has no seat at that table.

### Practical asymmetry: IP vs design

One nuance matters. Because both repos are Foundation-owned, the donation does not require a CLA or copyright assignment — Foundation IP is already Foundation IP. The NOTICE file update (§2 item 6) records the origin for attribution, not for legal transfer. This simplifies the acceptance process but does not change the governance model.

**Verdict: Donation model. MLFP is a first donor, not a permanent co-maintainer. After merge, Kailash owns the code; MLFP gets the same bug-report and PR process as any other user.**

---

## 2. Apache 2.0 Audit Checklist (Per Helper)

All seven helpers share the same header audit requirements. Per-helper deviations are noted.

### Universal checks (all 7 helpers)

| #   | Audit item                         | Requirement                                                                                                                                                                         | Status                                                                       |
| --- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1   | License header                     | Every `.py` file MUST have `# SPDX-License-Identifier: Apache-2.0` and `# Copyright 2026 Terrene Foundation`                                                                        | Verify — MLFP judges file shows the correct header; other helpers need sweep |
| 2   | No GPL/AGPL runtime deps           | None of `bert-score`, `rouge-score`, `sacrebleu`, `trl`, `peft`, `transformers`, `plotly`, `matplotlib` are GPL — all Apache 2.0 or BSD                                             | PASS — no viral licenses in the dependency set                               |
| 3   | NOTICE update                      | Root `NOTICE` and per-sub-package `NOTICE` files MUST add: "Portions derived from Terrene Foundation MLFP course material (https://github.com/terrene-foundation/mlfp), Apache 2.0" | ACTION REQUIRED — file does not currently reference MLFP origin              |
| 4   | No commercial SDK imports          | No `import openai`, `import anthropic`, `import langfuse`, `import litellm` in any contributed file                                                                                 | See per-helper finding below                                                 |
| 5   | No PII in comments or example data | No email addresses, names, real tokens, or real DB credentials in docstrings or test fixtures                                                                                       | Verify at PR-review time                                                     |
| 6   | Medical metaphor strip             | `Stethoscope`, `X-Ray`, `ECG`, `MRI`, `Endoscope` MUST be replaced per `rules/terrene-naming.md` § "Canonical Terminology"                                                          | ACTION REQUIRED — affects DLDiagnostics and others                           |
| 7   | CONTRIBUTORS attribution           | Add `Terrene Foundation MLFP course (https://github.com/terrene-foundation/mlfp)` to CONTRIBUTORS file at first merge                                                               | ACTION REQUIRED                                                              |

### Per-helper deviations

| Helper                         | Additional audit item                                                                                                                                                                               |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AgentDiagnostics               | **CRITICAL**: Langfuse hardcoded in exporter — MUST strip to `TraceExporter` Protocol before accepting. Run `grep -rn langfuse packages/kaizen-agents/` to confirm zero hits before PR approval.    |
| LLMDiagnostics + JudgeCallable | **HIGH**: `bert-score` pulls `transformers` + `torch` as transitive deps — MUST be in `kaizen[judges]` extra, MUST NOT bleed into base install. Verify with `pip show bert-score \| grep Requires`. |
| AlignmentDiagnostics           | `trl` fallback — drop per the offerer's note. `trl` is Apache 2.0 so not a legal risk, but the dead fallback code is a `rules/zero-tolerance.md` Rule 2 violation (stub).                           |
| GovernanceDiagnostics          | REJECTED for redesign — no separate Apache audit needed; methods absorbed into `GovernanceEngine` inherit that module's existing header.                                                            |

### Highest-impact Apache 2.0 audit finding

**The NOTICE file gap is the blocking item.** Kailash's NOTICE file (`/Users/esperie/repos/loom/kailash-py/NOTICE`) currently makes no reference to MLFP. Apache 2.0 Section 4(d) requires preserving attribution notices from contributed works. Because MLFP's files carry `Copyright 2026 Terrene Foundation`, the attribution is trivially satisfied by the copyright notice already being correct — but the NOTICE file update is the paper trail that proves provenance for downstream users who want to know where the diagnostic helpers came from. This is also the record that makes future "who owns what" questions answerable.

The Langfuse commercial import in AgentDiagnostics is the second-highest finding because it is a `rules/independence.md` violation at the runtime-dependency level: if `langfuse` ends up in a sub-package `pyproject.toml`, it becomes a dependency of every Kaizen user, not just MLFP course participants.

---

## 3. Community Extension Story

### The protocol surface

Per the architectural analysis (`proposal-pattern-architecture.md` Option E), the correct community extension interface is three stable protocols in `src/kailash/diagnostics/protocols.py` (core SDK, zero optional deps):

- **`Diagnostic` protocol** — context manager + `run_id` + `report() → DiagnosticReport` + optional `plot_*()` with loud-failure
- **`TraceEvent` JSON schema** — cross-SDK stable (span_id, cost_microdollars as integer, `tenant_id_fingerprint` as `sha256:<8 hex>`)
- **`JudgeCallable` protocol** — Delegate-wrapped LLM judge with typed `JudgeVerdict`

### How third parties contribute adapters

A third-party contributor (university course, enterprise customer, open-source project) who wants to donate a new diagnostic helper follows a 6-step flow that requires ZERO Foundation architecture discussion:

1. Inherit `kailash.diagnostics.Diagnostic` protocol.
2. Choose which of the 3 primitives the helper needs (`JudgeCallable` for LLM-evaluated diagnostics, `TraceEvent` for agent-trace diagnostics, neither for pure math diagnostics).
3. Ship in the domain package that owns the semantics — `kailash_ml.diagnostics.*` for ML-lifecycle helpers, `kaizen.diagnostics.*` for LLM/agent helpers, etc.
4. Land ONE wiring test at `tests/integration/test_<name>_diagnostics_wiring.py` proving real infrastructure + facade import path (`kailash_ml.YourDiagnostics`, not the internal module path).
5. Update `specs/diagnostics-catalog.md` with a one-line entry.
6. Submit PR — the `/redteam` mechanical sweep (`rg '*Diagnostics' packages/*/src/` + verify wiring test exists) catches any missing tests automatically.

### Core vs external package

The `Diagnostic` protocol and the three primitives are **Core** (live in `src/kailash/diagnostics/` — part of `pip install kailash`, zero heavy deps). Concrete diagnostic implementations are **Domain** (live in their respective sub-packages, pull their domain-specific deps via extras). There is no "external package" tier for diagnostics — the protocol is the stable surface, and implementations belong in the domain that owns their semantics.

The Foundation does NOT operate a third-party diagnostics registry. If a contributor's helper is generic enough, it merges into the relevant domain package. If it is too specialized (e.g., a company's proprietary evaluation rubric), it lives in that company's own package and depends on `kailash.diagnostics` for the protocol — the same relationship any Apache 2.0 downstream user has.

---

## 4. Framework-First Compliance Audit — LLMDiagnostics + JudgeCallable

### Source verified

Fetched `terrene-foundation/mlfp/main/shared/mlfp06/diagnostics/_judges.py` directly.

### Finding: PASS with one MEDIUM flag

**PASS — no raw OpenAI/Anthropic calls.** The file's docstring explicitly states: "raw `openai.chat.completions.create` is BLOCKED — every LLM call goes through `Delegate.run_sync`." The import block confirms: zero `import openai`, zero `import anthropic`, zero `import litellm`. The `JudgeCallable` class holds a `Delegate` instance and lazily constructs one via `_ollama_bootstrap.make_delegate()` on first call.

**PASS — env-models compliance.** Model resolution follows the priority chain `OLLAMA_JUDGE_MODEL → OLLAMA_CHAT_MODEL → OPENAI_JUDGE_MODEL → DEFAULT_LLM_MODEL → OPENAI_PROD_MODEL → bootstrap default`. No hardcoded model strings per `rules/env-models.md`.

**MEDIUM flag — cost tracking uses raw floats.**

The `JudgeVerdict` dataclass carries `score: float` and `latency_ms: float`. The budget tracking uses `self._call_count` (integer, correct), but the verdict's `score` field is a float `[0, 1]`. This is not a cost-tracking issue — the `JudgeCallable` itself does not accumulate USD totals; it delegates cost tracking entirely to the `Delegate.run_sync` call, which routes through `CostTracker` internally.

The MEDIUM flag is for the `JudgeVerdict.score: float` vs the Kailash convention of `cost_microdollars: int`. The verdict score is NOT a cost; it is a bounded evaluation score. The concern in `failure-points.md` §1.2 was about `AgentTrace.total_cost` summing floats — that concern is in AgentDiagnostics, not JudgeCallable. For JudgeCallable specifically, cost routing is clean.

**MEDIUM flag — `mode: "fake"` field.**

When budget is exhausted, `JudgeCallable` returns a verdict with `mode="fake"`. This is a `rules/zero-tolerance.md` Rule 2 concern: a verdict that claims to be real but is not. The fix at adaptation time: rename to `mode: Literal["real", "budget_exhausted"]` and ensure callers cannot treat `budget_exhausted` verdicts as scored output. `JudgeBudgetExhausted` typed error (as required by `failure-points.md` §1.2) is more architecturally correct than a fake-mode sentinel.

**Verdict for framework-first compliance:**

- LLMDiagnostics + JudgeCallable: **PASS** (no raw API calls). MEDIUM items require cleanup before merge but are not HIGH blockers.
- AgentDiagnostics: **MEDIUM** (CostTracker routing for `total_cost` — Langfuse strip is the HIGH item, CostTracker routing is the secondary cleanup).
- No HIGH blocker from the framework-first audit on the judges module.

---

## 5. Maintenance Story

### Test tier requirements

Every accepted helper MUST meet the testing contract from `rules/testing.md`:

- **Tier 1 (unit)**: Required for pure-math helpers (RAGDiagnostics metric math, AlignmentDiagnostics KL/reward-margin). No mocking of framework surfaces.
- **Tier 2 (integration, real infrastructure)**: MANDATORY for every helper that has a framework facade (`kailash_ml.DLDiagnostics`, `kaizen.judges.LLMJudge`, etc.) per `rules/facade-manager-detection.md` Rule 1. Test file named `test_<name>_diagnostics_wiring.py`. Exercises real infra (PostgreSQL for trace persistence, real model via `.env` for judge calls).
- **Tier 3 (E2E)**: Not required for initial donation. Added by the Foundation when the diagnostic surface becomes user-facing in documentation.

### Deprecation policy

The `Diagnostic` protocol and three primitives in core SDK are **stable API** on landing (they are the contract; breaking them breaks all seven helpers simultaneously). Major-version deprecation lane applies: minimum 2 minor releases with `DeprecationWarning` before removal.

Domain-specific diagnostic classes (`DLDiagnostics`, `RAGDiagnostics`, etc.) follow the sub-package's own deprecation policy. Currently kailash-ml and kailash-kaizen are pre-1.0, which allows minor-version breaking changes under SemVer; once they hit 1.0, the same 2-minor-release lane applies.

### CODEOWNERS

The diagnostic surface spans four sub-packages. Ownership by framework:

| File / package                                                                   | Owner                                               |
| -------------------------------------------------------------------------------- | --------------------------------------------------- |
| `src/kailash/diagnostics/`                                                       | Foundation Core Team (same as `src/kailash/trust/`) |
| `packages/kailash-ml/src/kailash_ml/diagnostics/`                                | ml-specialist domain                                |
| `packages/kailash-kaizen/src/kaizen/judges/`                                     | kaizen-specialist domain                            |
| `packages/kailash-kaizen/src/kaizen/interpretability/`                           | kaizen-specialist domain                            |
| `packages/kailash-kaizen/src/kaizen/core/autonomy/observability/agent_traces.py` | kaizen-specialist domain                            |
| `packages/kailash-align/src/kailash_align/diagnostics.py`                        | align-specialist domain                             |

### Breaking-change deprecation lane

Any change to the `Diagnostic` protocol, `TraceEvent` JSON schema, or `JudgeCallable` protocol that alters the wire format (field rename, type change, required field addition) MUST:

1. Bump the schema version in `src/kailash/diagnostics/protocols.py`.
2. File a cross-SDK parity issue in `esperie/kailash-rs` before merging.
3. Provide a migration shim for one minor version.
4. Remove the shim in the next minor version.

This is identical to the pattern already in place for `TrainingResult` changes in kailash-ml (see `specs/ml-engines.md`).

---

## 6. Versioning Impact and SemVer Stance

### Decision: `[diagnostics]` extras gate, 0.x experimental tier

The core SDK `kailash.diagnostics` protocols module introduces zero new optional deps — it is pure Python (Protocols, dataclasses, stdlib). It ships as part of `pip install kailash` with no extras gate.

Domain helpers ship behind their domain sub-package's existing extras:

| Helper                           | Package        | Extra                                  | Recommended version      |
| -------------------------------- | -------------- | -------------------------------------- | ------------------------ |
| DLDiagnostics                    | kailash-ml     | `kailash-ml[dl]` (+matplotlib)         | kailash-ml 0.18.0        |
| RAGDiagnostics                   | kailash-ml     | No new extra                           | kailash-ml 0.18.x        |
| LLMDiagnostics + JudgeCallable   | kailash-kaizen | NEW `kailash-kaizen[judges]`           | kailash-kaizen 2.9.0     |
| InterpretabilityDiagnostics      | kailash-kaizen | NEW `kailash-kaizen[interpretability]` | kailash-kaizen 2.9.x     |
| AgentDiagnostics                 | kailash-kaizen | No new extra (after Langfuse strip)    | kailash-kaizen 2.9.x     |
| AlignmentDiagnostics             | kailash-align  | Existing extras                        | kailash-align next-minor |
| GovernanceDiagnostics (redesign) | kailash-pact   | No new extra                           | kailash-pact 0.9.0       |

**SemVer stance: 0.x experimental for domain helpers, stable for core protocols.**

The three core-SDK protocols (`Diagnostic`, `TraceEvent`, `JudgeCallable`) are published as stable the moment PR#0 merges — they are the contract, and instability in the contract defeats the purpose. Domain helpers ship at the sub-package's current version cadence (kailash-ml is 0.x, kailash-kaizen is pre-2.10, all accept minor-version breaking changes).

There is no `[diagnostics]` meta-extra at the root `kailash` package. The domain extras (`ml[dl]`, `kaizen[judges]`) are the natural discovery path. A `kailash[diagnostics]` meta-extra that pulls all 7 helpers would create an accidental full-stack test dependency that violates `rules/python-environment.md` Rule 4 (sub-package test deps in root).

---

## 7. Strategic Recommendation

**Recommendation: Extract primitives first (Option E — `proposal-pattern-architecture.md`), then accept domain adapters sequentially.**

This is not a pure "accept selectively" or a pure "accept in full." It is a structural reordering: ship the contract before shipping the code that implements it.

### The 8-PR sequence

**PR#0** (1 session, blocks everything): `src/kailash/diagnostics/protocols.py` — `Diagnostic` protocol, `TraceEvent` schema, `JudgeCallable` protocol, `DiagnosticReport` frozen base, `DiagnosticPlotUnavailable` error. Zero optional deps, zero domain logic. This is the only PR that requires a cross-SDK parity ticket filed before it merges (kailash-rs mirrors the JSON schema).

**PR#1–PR#7**: Per `failure-points.md` §3 table (DLDiagnostics → RAGDiagnostics → LLMDiagnostics → InterpretabilityDiagnostics → AgentDiagnostics → AlignmentDiagnostics → GovernanceDiagnostics redesign), each in its own PR with per-helper specialist ownership.

**Total autonomous execution estimate**: ~5–6 sessions (PR#0 is 1 session; PR#1/PR#3/PR#6/PR#7 parallelize after PR#0; PR#2/PR#4/PR#5 append sequentially to their package owners).

### Why not the alternatives

**Accept in full (single PR):** Blocked by `rules/autonomous-execution.md` session budget (7,300 LOC × 4 packages × ~3 invariants each = well above the ≤500 LOC / ≤10 invariants shard limit). Single-PR acceptance replicates the Phase 5.11 failure mode exactly.

**Accept selectively (take 4, defer 3):** Loses the architectural coherence benefit. If DLDiagnostics ships without the `Diagnostic` protocol, the 8th helper will argue for its own shape. The protocol cost is one small PR; paying it once makes all 7 helpers and all future helpers coherent.

**Reject / build from scratch:** The MLFP code is already Foundation IP and already framework-first compliant (confirmed by live source audit). Building from scratch wastes the existing Foundation investment and delays the surface by multiple sessions.

**Extract primitives first:** This is the recommendation. The 3-primitive + 7-domain-adapter shape is the only option that simultaneously satisfies `rules/orphan-detection.md` (wiring tests by construction), `rules/framework-first.md` (domain-package binding), `rules/independence.md` (no MLFP structural dependency), and the community extension story (8th helper is additive, not architectural).

### Key pre-merge gates

Before any PR merges:

1. **NOTICE file updated** — add MLFP origin attribution per Apache 2.0 Section 4(d).
2. **Langfuse zero** — `grep -rn langfuse packages/kaizen-agents/` must return zero results.
3. **Medical metaphor zero** — cross-helper grep regression test passes (per `failure-points.md` §2.3 test).
4. **Cross-SDK parity issues filed** — 4 mandatory items (`esperie/kailash-rs` issues for LLMDiagnostics, RAGDiagnostics, AgentDiagnostics, GovernanceDiagnostics redesign) open before PR#0 merges.
5. **`mode="fake"` refactored** — `JudgeVerdict.mode` becomes `Literal["real", "budget_exhausted"]`; budget-exhausted path raises `JudgeBudgetExhausted` per `rules/zero-tolerance.md` Rule 3 (no silent fallback).

---

## Appendix: Framework-First Audit Evidence

**Source URL**: `https://raw.githubusercontent.com/terrene-foundation/mlfp/main/shared/mlfp06/diagnostics/_judges.py`

**Key findings from live fetch (2026-04-20)**:

- Copyright header: `# Copyright 2026 Terrene Foundation` + `# SPDX-License-Identifier: Apache-2.0` — PASS
- Top-level imports: stdlib only (`logging`, `os`, `re`, `threading`, `time`, `uuid`, `dataclasses`, `typing`, `dotenv`) — zero commercial SDK imports — PASS
- Delegate usage: `JudgeCallable._ensure_delegate()` calls `shared.mlfp06._ollama_bootstrap.make_delegate(model=..., system_prompt=..., temperature=0.0)` — routes through Kaizen Delegate, not raw API — PASS
- Model resolution: `resolve_judge_model()` chains env vars in the correct order per `rules/env-models.md` — PASS
- Cost routing: no float accumulation in JudgeCallable itself; Delegate handles cost internally — PASS
- `mode="fake"` sentinel: present (MEDIUM flag — refactor to typed error before merge)
- `_parse_score()` uses `re.findall` on free text — this IS a `rules/agent-reasoning.md` MUST Rule 3 concern: regex on free-text judge output rather than structured `OutputField`. MEDIUM flag: wire `JudgeVerdict.score` through a structured Signature rather than post-hoc regex parsing. The MLFP implementation works but the regex approach is brittle and violates the LLM-first rule.
