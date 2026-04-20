# kailash-align Changelog

## [0.4.0] - 2026-04-20

### Added

- **AlignmentDiagnostics adapter** (issue #567, PR#3 of 7): concrete Align adapter satisfying `kailash.diagnostics.protocols.Diagnostic` (landed PR#0/#570). Observes LLM fine-tuning runs via three primary readings:
  - `evaluate_pair(base_logprobs, tuned_logprobs, preferences)` — closed-form KL(base || tuned), reward-margin, pairwise win-rate
  - `track_training(metrics_iterable)` — bounded-memory deque ingestion of `{step, reward, kl, loss, ...}` dicts from `AlignmentPipeline.metrics_stream()` or equivalent
  - `detect_reward_hacking(threshold=2.5)` — flags the canonical signature of sudden reward spike co-occurring with a KL blow-up
- `report()` returns structured dict with severity-tagged findings; never raises on empty state
- `plot_*()` methods return plotly Figures via `_require_plotly()` loud-fail helper
- `*_df()` accessors return polars DataFrames
- Closed-form KL primary path (numpy); `trl` statistical helpers used as an optimization when available

### Attribution

- Portions originated from MLFP (Apache-2.0) and re-authored for the Kailash ecosystem — see `specs/alignment-diagnostics.md` § "Attribution" for the full donation history.

## [0.2.0] - 2026-04-02

### Fixed

- **AdapterRegistry bounded** (C1): max_adapters=10,000, max_versions_per_adapter=1,000 — prevents OOM
- **Shell script sanitization** (C2): Generated launch_vllm.sh sanitizes adapter_name via regex
- **Subprocess flag injection** (H1): `--` separator added before path arguments in GGUF conversion
- **Division-by-zero guards** (H2/H3): `max(1, total_params)` in pipeline.py, `max(1, hidden_dim_estimate)` in gpu_memory.py

### Security

- R3 red team converged: 0 CRITICAL, 0 HIGH findings
- 391 tests passing, 0 regressions

## [0.1.0] - 2026-03-30

### Added

- Initial release: 12 alignment methods, MethodRegistry, AlignmentPipeline, AdapterRegistry, AlignmentEvaluator, AlignmentServing, KaizenModelBridge, OnPremModelCache
