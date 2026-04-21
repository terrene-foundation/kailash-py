# Spec — Kaizen Judges (LLM-as-Judge)

**Status:** Authoritative as of 2026-04-20 (PR#5 of 7, issue #567).
**Package:** `kailash-kaizen` (v2.9.0+).
**Module:** `kaizen.judges`.
**Protocol:** `kailash.diagnostics.protocols.JudgeCallable` + `Diagnostic` (landed PR#0/#570).

## Purpose

`kaizen.judges` is the Kaizen-side concrete implementation of the cross-SDK `JudgeCallable` Protocol plus the diagnostic-session wrapper `LLMDiagnostics`. It exists to let downstream adapters (kailash-ml `RAGDiagnostics`, kailash-align `AlignmentDiagnostics`, third-party judges) dispatch judgment calls through a single framework-first entry point that:

1. **Routes every LLM call through `kaizen_agents.Delegate`** — no raw `openai.chat.completions.create` / `litellm.completion` per `rules/zero-tolerance.md` Rule 4 + `rules/framework-first.md`.
2. **Uses structured `Signature(InputField/OutputField)` for scoring** — no regex on LLM output per `rules/agent-reasoning.md` MUST Rule 3.
3. **Tracks spend in integer microdollars through `kaizen.cost.tracker.CostTracker`** — same integer-microdollar contract as `pact.costs.CostTracker` for cross-SDK parity (no raw USD floats).
4. **Raises typed `JudgeBudgetExhaustedError` when the cap is hit** — no silent partial-success payloads per `rules/zero-tolerance.md` Rule 3.

## Public surface (facade import per `rules/orphan-detection.md` §1)

```python
from kaizen.judges import (
    LLMJudge,                        # JudgeCallable Protocol impl (async)
    LLMDiagnostics,                  # Diagnostic Protocol session wrapper
    FaithfulnessJudge,               # RAG-grounding rubric wrapper
    SelfConsistencyJudge,            # N-sample variance wrapper
    SelfConsistencyReport,           # frozen result dataclass
    RefusalCalibrator,               # benign/harmful refusal rate metric
    JudgeBudgetExhaustedError,       # typed error
    resolve_judge_model,             # env-sourced model resolution
)
```

## `LLMJudge(budget_microdollars, *, judge_model=None, tenant_id=None, sensitive=False, delegate=None, run_id=None)`

Concrete implementation of `kailash.diagnostics.protocols.JudgeCallable`.

### Invariants

1. `isinstance(j, JudgeCallable)` returns `True` at runtime (the Protocol is `@runtime_checkable`).
2. `budget_microdollars` MUST be a non-negative `int`. `bool` is BLOCKED (type-safe integer guard).
3. `run_id` (post-construction) is a non-empty string — UUID4 hex when omitted; the user-supplied value MUST be non-empty.
4. `judge_model` is resolved from env (`KAIZEN_JUDGE_MODEL` → `OPENAI_JUDGE_MODEL` → `DEFAULT_LLM_MODEL` → `OPENAI_PROD_MODEL`) when omitted per `rules/env-models.md`. No hardcoded model strings in code.
5. `delegate` — optional pre-constructed `kaizen_agents.Delegate`. When omitted, the judge constructs one scoped to `budget_microdollars`. Test code passes a scripted delegate here (Tier 1); production uses the default.

### `async __call__(judge_input: JudgeInput) -> JudgeResult`

Dispatches either pointwise (`candidate_b is None`) or pairwise (`candidate_b is not None`) scoring. Pairwise runs position-swap bias mitigation: two LLM calls with A/B swapped, aggregated by `_resolve_winner` with deterministic tie-break.

**Budget enforcement**: the cumulative spend tracked on `self._spent_microdollars` is compared against `budget_microdollars` AFTER each LLM call. When the cap is exceeded, `JudgeBudgetExhaustedError` is raised at the boundary of the next call — the in-flight call's partial cost is reflected in `spent_microdollars` but the caller receives the typed error, NOT a half-populated `JudgeResult`.

**No regex on output**: the LLM produces a structured `Signature(OutputField)` with `score` / `winner` / `reasoning` fields; `_parse_score` heuristics from the MLFP donor source were replaced with Signature-based parsing.

### Attributes (duck-type surface for `LLMDiagnostics`)

- `budget_microdollars: int`
- `spent_microdollars: int` (property)
- `judge_model: str`

## `LLMDiagnostics(*, judge=None, default_budget_microdollars, max_history, sensitive, tenant_id, run_id)`

Context-managed `Diagnostic` session. Aggregates four judgment axes into one report.

### Methods

```python
def llm_as_judge(
    self, *, prompt, response, rubric,
    candidate_b=None, reference=None, sub_run_id=None,
) -> JudgeResult: ...

def faithfulness(
    self, response, context, *, prompt=None, sub_run_id=None,
) -> JudgeResult: ...

def self_consistency(
    self, prompt, response, *, rubric, reference=None,
    n_samples=3, sub_run_id=None,
) -> SelfConsistencyReport: ...

def refusal_calibrator(
    self, *, benign_prompts, benign_responses,
    harmful_prompts=None, harmful_responses=None,
    label="sample", sub_run_id=None,
) -> dict: ...
```

All four methods surface rows to polars DataFrames via `judge_df()` / `faithfulness_df()` / `consistency_df()` / `refusal_df()`. The buffered history is bounded via `deque(maxlen=max_history)` (default 1024).

### Protocol conformance

- `isinstance(diag, Diagnostic)` is `True` at runtime.
- `diag.run_id: str` — session correlation id (also present on every log line as `llm_diag_run_id`).
- `diag.__enter__() -> LLMDiagnostics` / `diag.__exit__(*exc) -> None` — never raises; `JudgeBudgetExhaustedError` propagates to the caller, caught only when the user explicitly does so.

### `report() -> dict`

Fields:

- `run_id: str`
- `judge_calls: int`
- `faithfulness_checks: int`
- `consistency_sweeps: int`
- `refusal_samples: int`
- `total_cost_microdollars: int`
- `judge_summary` / `faithfulness_summary` / `consistency_summary` / `refusal_summary` — each `{severity, message}` with severity in `{"HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"}`.

`report()` never raises on empty state.

## Judge wrappers

### `FaithfulnessJudge(base_judge: LLMJudge)`

- Fixed rubric: `"faithfulness,grounded_in_context,no_fabrication"`.
- Delegates scoring to the provided `LLMJudge`; adds no new LLM surface.
- Strict typing: requires an `LLMJudge` instance (not any `JudgeCallable`). The wrapper needs attributes (`budget_microdollars` / `spent_microdollars`) that only `LLMJudge` guarantees.

### `SelfConsistencyJudge(base_judge: LLMJudge, n_samples: int)`

- Runs `n_samples` independent scorings through ONE shared `CostTracker` via `base_judge`.
- Returns frozen `SelfConsistencyReport(mean_score, stdev_score, n_samples, total_cost_microdollars, ...)`.
- `n_samples >= 1`; lower values disable variance estimation and surface `stdev_score=0.0`.
- Propagates `JudgeBudgetExhaustedError` mid-sweep — per `rules/zero-tolerance.md` Rule 3 the caller decides whether to increase the budget or reduce `n_samples`.

### `RefusalCalibrator(base_judge: LLMJudge)`

- Scores over-refusal + under-refusal rates across paired benign/harmful prompt sets.
- Returns a plain dict (NOT a frozen dataclass — shape evolves with the rubric).

## Position-swap bias mitigation

For pairwise judgments, `LLMJudge.__call__` executes two scorings with A/B swapped and calls `_resolve_winner(pref_a, pref_a_swap)` to aggregate:

- Both orderings prefer the same candidate → return that winner.
- Orderings disagree → return `"tie"` (flag for human review, never silently average).
- Either ordering returns `None` → defer to the other; both `None` → `"tie"`.

Tie-break is deterministic: no randomness, no position preference. This is the structural defense against position bias per `rules/agent-reasoning.md` Rule 3 — the LLM reasons, the aggregator is deterministic code operating on the LLM's structured output.

## Security threats

| Threat                              | Mitigation                                                                                                                                                                                                                                                                |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Prompt injection via candidate text | The judge's Signature carries the candidate as a structured `InputField` (not interpolated into the system prompt). A malicious candidate that tries to issue instructions is seen as data, not directive. Downstream defense: `sensitive=True` redacts previews in logs. |
| Position bias on pairwise judgments | Two swapped calls + deterministic aggregator (`_resolve_winner`); disagreements flagged as ties rather than averaged. No randomness in aggregation.                                                                                                                       |
| Cost blow-up from runaway loops     | `JudgeBudgetExhaustedError` raised AFTER any call that exceeds the cap; caller sees typed error, not silent over-spend.                                                                                                                                                   |
| Sensitive payload leakage to logs   | `sensitive=True` mode redacts prompt/response previews to `<redacted>`. Default 120-char preview otherwise. Full payloads NEVER logged at INFO. Matches `rules/observability.md` discipline.                                                                              |
| Tenant cross-contamination          | `tenant_id` is tracked on every judge + entry; `LLMDiagnostics` logs it on every structured line. Cross-tenant CostTracker sharing BLOCKED per `rules/tenant-isolation.md` Rule 5.                                                                                        |
| Hardcoded API keys                  | `rules/env-models.md` — every judge reads model from env; raw API keys appear only via `openai.api_key` / `anthropic.api_key` populated from `.env` by `load_dotenv()` at session start. No secrets in code.                                                              |
| Regex-based winner selection        | BLOCKED by `rules/agent-reasoning.md` Rule 3. Winner comes from `OutputField(description="winner")` parsed by Signature — the only drift defense against a refactor that "restores" regex heuristics.                                                                     |

## Test discipline

Per `rules/testing.md` 3-tier model:

- **Tier 1 (unit)** — `packages/kailash-kaizen/tests/unit/judges/test_judges_unit.py` (24 tests): Protocol conformance, pointwise / pairwise scoring via scripted `_ScriptedDelegate`, position-swap aggregation, budget-exhaust typed error raise, input validation, `_clamp_unit` + `_resolve_winner` helper math.
- **Tier 2 (integration)** — `packages/kailash-kaizen/tests/integration/judges/test_judges_wiring.py` (7 tests): **facade-import required** (`from kaizen.judges import LLMDiagnostics`), Protocol conformance via facade, `DeterministicJudge` (non-mock, Protocol-satisfying test adapter), end-to-end `llm_as_judge` against real polars + plotly, async Protocol smoke check, plot dashboard empty-state non-raise.

Per `rules/orphan-detection.md` §1 the Tier 2 file MUST import the adapters through the package facade (`kaizen.judges`), NOT direct module paths (`kaizen.judges._judge`, `kaizen.judges.llm_diagnostics`).

The `integration` marker is registered in `packages/kailash-kaizen/pyproject.toml [tool.pytest.ini_options] markers` per `rules/testing.md` "Pytest Plugin + Marker Declaration Pair".

## Observability

Every emitted log line carries `extra={"llm_diag_run_id": self.run_id, ...}`. Field names are domain-prefixed (`llm_diag_*`, `llm_judge_*`) to avoid `LogRecord`-reserved-name collision documented in `rules/observability.md` Rule 9. `mode=real` field appears on the hot-path logs so `grep mode=fake` surfaces any accidental stub (per `rules/observability.md` §3).

## Cross-SDK parity

`LLMJudge` and `LLMDiagnostics` follow the Protocols pinned in `src/kailash/diagnostics/protocols.py` + `schemas/trace-event.v1.json`. A future kailash-rs crate (scope of BP-052 in the issue-567 synthesis plan) implements the same Protocols with matching `report()` key shapes.

## Attribution

Portions of `LLMJudge` / `LLMDiagnostics` / the wrapper judges originated in the **Machine Learning From Practice** (MLFP) course diagnostics library (`shared/mlfp06/diagnostics/output.py` + `_judges.py`, Apache 2.0) and were re-authored for the Kailash ecosystem under the following cleanups:

- Medical metaphors ("Stethoscope" lens metaphor) stripped per `rules/terrene-naming.md`.
- `_parse_score` regex heuristics REPLACED with structured Signature-based parsing per `rules/agent-reasoning.md` Rule 3.
- Raw `openai.*` / `litellm.*` calls ROUTED through `kaizen_agents.Delegate` per `rules/framework-first.md`.
- USD-float cost accumulation REPLACED with integer-microdollar `kaizen.cost.tracker.CostTracker` (same integer-microdollar contract as `pact.costs.CostTracker` for cross-SDK parity).
- Partial-success on budget overflow REPLACED with typed `JudgeBudgetExhaustedError` per `rules/zero-tolerance.md` Rule 3.
- Frozen result dataclasses + `__exit__` non-raise contract added.

The MLFP donation history is recorded in the root `NOTICE` file per Apache-2.0 §4(d) (blocker B4 of issue #567 shipped in #569).

## Origin

- Issue: [`kailash-py#567`](https://github.com/terrene-foundation/kailash-py/issues/567).
- Donation PRs in sequence: #569 (blockers), #570 (protocols PR#0), #571 (DLDiagnostics PR#1), #574 (AlignmentDiagnostics PR#3), #575 (RAGDiagnostics PR#2), #576 (InterpretabilityDiagnostics PR#4), #578 (PACT absorb PR#7), this PR (LLMDiagnostics + JudgeCallable PR#5).
- Protocol contract: `src/kailash/diagnostics/protocols.py::JudgeCallable` + `Diagnostic`.
- Plan: `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md`.
