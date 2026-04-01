# kailash-align Changelog

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
