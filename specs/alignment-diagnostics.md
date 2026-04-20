# Spec — Alignment Diagnostics

**Status:** Authoritative as of 2026-04-20 (PR#3 of 7, issue #567).
**Package:** `kailash-align` (v0.4.0+).
**Module:** `kailash_align.diagnostics`.
**Protocol:** `kailash.diagnostics.protocols.Diagnostic` (landed PR#0/#570).

## Purpose

`AlignmentDiagnostics` is the concrete kailash-align adapter that satisfies the cross-SDK `Diagnostic` Protocol for an LLM fine-tuning / alignment run. It observes the training signal rather than running it: consumes preference tuples, per-token log-probability arrays, and metric streams from the Align trainer, and emits severity-tagged findings covering:

1. **Pair evaluation** — KL(base || tuned), pairwise reward margin, pairwise win-rate.
2. **Training-curve tracking** — bounded-memory ingestion of `{step, reward, kl, loss, ...}` dicts from any `metrics_stream()`-yielding trainer.
3. **Reward-hacking detection** — the canonical reward-spike + KL-blowup signature over the training buffer.

It installs **no hooks** and loads **no model weights**. The heavy training lives in `kailash_align.AlignmentPipeline` (or any equivalent trainer); this lens observes its output.

## Surface

### Construction

```python
from kailash_align.diagnostics import AlignmentDiagnostics

with AlignmentDiagnostics(
    label="dpo_run42",
    window=10_000,             # max training steps kept in memory (FIFO evict)
    run_id=None,               # optional correlation id; UUID4 hex when omitted
) as diag:
    ...
```

**Invariants:**

- `label` MUST be a non-empty string (`ValueError` otherwise).
- `window` MUST be `>= 1`.
- `run_id` when provided MUST be non-empty.
- `diag.run_id` (post-construction) is always a non-empty string; external logs use it for correlation.

### Protocol conformance

`isinstance(diag, kailash.diagnostics.protocols.Diagnostic)` returns `True` at runtime because the Protocol is `@runtime_checkable`. The adapter exposes:

- `run_id: str` — session correlation id
- `__enter__() -> AlignmentDiagnostics`
- `__exit__(exc_type, exc_val, exc_tb) -> None` — never raises; no hooks to detach
- `report() -> dict` — never raises on empty state

### `evaluate_pair(base_policy, tuned_policy, preferences, *, label=None) -> pl.DataFrame`

Computes closed-form KL(base || tuned) over paired per-token log-probabilities, the preference-set reward margin, and the pairwise win-rate.

- `base_policy`, `tuned_policy`: `Sequence[Sequence[float]]` — per-example token log-probs (length `N`, each a variable-length float sequence). Lengths MUST match (`ValueError` otherwise).
- `preferences`: `Sequence[dict]` — each dict may contain `chosen_reward` (float), `rejected_reward` (float), `chosen_won` (truthy). Missing keys default to `0.0` / `False`.
- Returns a one-row polars DataFrame with schema `{label: Utf8, kl_divergence: Float64, reward_margin: Float64, win_rate: Float64, n: Int64}`.
- Empty preferences → `reward_margin` / `win_rate` are `NaN` (undefined for empty sample).

### `kl_divergence(p_logprobs, q_logprobs) -> float`

Closed-form estimator over paired per-token log-probs: `mean(p - q)` with per-token clipping. Matches the `evaluate_pair` internal path. When `trl.trainer.utils.kl_divergence` + torch are both importable, uses them as a numerical optimization; behaviorally equivalent to the closed-form path up to floating-point rounding.

### `win_rate(preferences) -> float`

Fraction of preference rows where `chosen_won` is truthy. Returns `NaN` for empty input.

### `track_training(metrics) -> pl.DataFrame`

Accepts either (a) an iterable of `{step, reward, kl, loss, ...}` dicts, or (b) any object exposing `metrics_stream()` (callable → iterable) or a `metrics` attribute — matches `AlignmentPipeline` and any ad-hoc trainer using that convention.

- Missing fields default to `float("nan")`; extras preserved in internal `_TrainingStep.extras` but not surfaced in the returned DataFrame (stable 4-column schema `{step, reward, kl, loss}`).
- Buffer is memory-bounded at `window` steps (FIFO evict on overflow — documented behaviour, not a bug).

### `detect_reward_hacking(history=None, *, threshold=2.5, label=None) -> pl.DataFrame`

Flags steps where `(reward[t] - reward[t-1]) / stdev(rewards) > threshold` AND `kl[t] > max(median(kl) * 1.5, 0.05)`. Both conditions required — spurious reward spikes with normal KL do NOT flag.

- `threshold` MUST be positive (`ValueError` otherwise).
- `history=None` uses the internal buffer; otherwise uses the supplied sequence.
- Findings emitted as one-row-per-step polars DataFrame with schema `{step, reward_zscore, kl_value, reward_value, label}`.
- Empty / sub-4-step history → empty DataFrame (not an error).
- When findings are present, emits one WARN log line `"alignment.reward_hacking.detected"` carrying `run_id`, `n_findings`, and `threshold_z` — no schema / column / PII content per `rules/observability.md` §8.

### `report() -> dict`

Aggregated session report. Never raises on empty state. Fields:

- `run_id: str` — matches `self.run_id`.
- `pairs: int` — count of `evaluate_pair` readings.
- `training_steps: int` — count of steps in the training buffer.
- `reward_hacking_findings: int` — count of flagged steps.
- `pair_summary: {severity, message}` — findings over pair log.
- `training_summary: {severity, message}` — findings over training buffer.
- `reward_hacking: {severity, message}` — findings over hack log.

Severity values are `"HEALTHY"` / `"WARNING"` / `"CRITICAL"` / `"UNKNOWN"`.

### DataFrame accessors

- `pair_df()` — cumulative pair-reading log (polars).
- `training_df()` — buffered training-step history (polars).
- `findings_df()` — all recorded reward-hacking findings (polars).

All return typed-schema empty DataFrames when the underlying log is empty (never raise).

### Plot methods

- `plot_training_curves()` → reward + KL curves over step; returns `plotly.graph_objects.Figure`.
- `plot_alignment_dashboard()` → 4-panel composite (reward, KL, pair summary, findings).
- Empty state produces a titled placeholder figure (no raise).
- All plot methods route through `_require_plotly()` which raises a loud, actionable `ImportError` naming the remediation if plotly is stripped — matches the `DLDiagnostics` pattern.

## Invariants

1. **Protocol conformance** (`rules/orphan-detection.md` §1): every `AlignmentDiagnostics` instance passes `isinstance(_, Diagnostic)`.
2. **Facade import required** for Tier 2 coverage: `from kailash_align.diagnostics import AlignmentDiagnostics` — importing `kailash_align.diagnostics.alignment` directly bypasses the facade contract.
3. **Bounded memory**: the training buffer MUST be a `deque(maxlen=window)`; unbounded lists are BLOCKED per the analysis `1.3/1.4` warning carried forward from DLDiagnostics.
4. **Log discipline** (`rules/observability.md`):
   - DEBUG: every `__init__`, `evaluate_pair`, `track_training`, construction-resolver probe.
   - WARN: `reward_hacking.detected` when findings > 0 — no schema / column / value content.
   - No `print`, no unstructured f-string log messages.
5. **Closed-form KL primary**, trl-as-optimization: the closed-form numpy path is the correctness contract; trl helpers are a numerical optimization only. This is the opposite of the MLFP source (which made closed-form the fallback); see § "Attribution" for the rewrite rationale.
6. **Medical-metaphor sweep**: `grep -ri 'stethoscope\|x-ray\|ECG\|flight recorder\|endoscope' packages/kailash-align/` MUST return empty per `rules/terrene-naming.md`.

## Security threats

| Threat                                                                                               | Mitigation                                                                                                                                                                                               |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reward-hacking false negatives — an attacker tunes a model to reward-hack along a non-KL-blowup axis | The detector is explicitly one heuristic; the spec requires operators to pair it with holdout-set eval from `alignment-serving.md`. This adapter never claims to be the sole reward-hacking defence.     |
| Leaking preference data in logs                                                                      | All log lines carry `run_id` + `n` + scalar stats only. Preference values, token-level log-probs, and raw reward scores are never logged. `rules/observability.md` §8 upheld.                            |
| Unbounded-memory training ingestion                                                                  | `deque(maxlen=window)`; default `window=10_000`. Operators explicitly set `window=0` (raises) or a tighter bound for low-RAM trainers.                                                                   |
| Divergence between `base_policy` and `tuned_policy` shapes                                           | Length mismatch raises `ValueError` at `evaluate_pair`. Per-token inner-length mismatch is handled by the closed-form estimator (paired per-token `p - q` on the shorter prefix — documented behaviour). |
| Reward-hacking false positives when trainer emits `NaN` loss/reward during early warmup              | `detect_reward_hacking` skips rows where `reward` or `kl` is `NaN`; the sigma floor (`1e-9`) prevents div-by-zero when the reward series is constant.                                                    |
| Plot methods breaking in a stripped install                                                          | `_require_plotly()` raises a named `ImportError` rather than a bare `ModuleNotFoundError`. `report()` and every `*_df()` accessor remain functional without plotly.                                      |

## Test discipline

Per `rules/testing.md` 3-tier model:

- **Tier 1 (unit)** — `packages/kailash-align/tests/unit/test_alignment_diagnostics_unit.py`: Protocol conformance, math assertions (identical policies → KL=0; divergent → KL>0), win-rate math, `detect_reward_hacking` behavioural assertion over a crafted spike, bounded-window FIFO, `report()` empty-state non-raise.
- **Tier 2 (integration)** — `packages/kailash-align/tests/integration/test_alignment_diagnostics_wiring.py`: **facade-import required** (`from kailash_align.diagnostics import AlignmentDiagnostics`), full `evaluate_pair → track_training → detect_reward_hacking → report()` round-trip, polars + plotly real-backend exercise, run_id correlation through the report surface.

The `integration` marker is registered in `packages/kailash-align/pyproject.toml [tool.pytest.ini_options] markers` per `rules/testing.md` "Pytest Plugin + Marker Declaration Pair".

## Observability

Every emitted log line carries `extra={"alignment_run_id": self.run_id, ...}`. The field name is domain-prefixed (`alignment_run_id` not `run_id`) to avoid the `LogRecord`-reserved-name collision documented in `rules/observability.md` §9.

## Cross-SDK parity

`AlignmentDiagnostics` follows the `Diagnostic` Protocol pinned in `schemas/trace-event.v1.json` + `src/kailash/diagnostics/protocols.py`. A future kailash-rs adapter crate (scope of BP-053 in the issue-567 synthesis plan) implements the same Protocol with matching `report()` key shapes.

## Attribution

Portions of the adapter were originally contributed from the **Machine Learning From Practice** (MLFP) course diagnostics library (`shared/mlfp06/diagnostics/alignment.py`, Apache 2.0) and re-authored for the Kailash ecosystem under the following cleanups:

- Medical metaphors ("ECG", "lens 5") stripped per `rules/terrene-naming.md`.
- Closed-form KL promoted from fallback to primary path; trl demoted to optimization.
- Structured logging, `run_id` correlation, and `_require_plotly()` gating added.
- Frozen dataclasses, typed-error surface, and `__exit__` non-raise contract added.
- Docstrings rewritten against the kailash Protocol, not the pedagogical "five-lens" framing.

The MLFP donation history is recorded in the root `NOTICE` file per Apache-2.0 §4(d) (blocker B4 of issue #567).

## Origin

- Issue: [`kailash-py#567`](https://github.com/terrene-foundation/kailash-py/issues/567).
- Donation PRs in sequence: #569 (blockers), #570 (protocols PR#0), #571 (DLDiagnostics PR#1), this PR (AlignmentDiagnostics PR#3).
- Protocol contract: `src/kailash/diagnostics/protocols.py::Diagnostic`.
- JSON schema of sibling `TraceEvent`: `schemas/trace-event.v1.json`.
- Plan: `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md`.
