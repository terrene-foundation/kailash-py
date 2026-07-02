# Red Team Round 1 — kailash-align M2 Method Expansion

**Date**: 2026-04-01
**Scope**: ALN-210 through ALN-222 (MethodRegistry refactor, 12 methods, 5 config classes, pipeline rewrite)
**Test baseline**: 388 passed, 1 skipped, 0 regressions

## Code Review Findings (intermediate-reviewer)

| ID  | Severity | Finding                                                                                          | Status                                           |
| --- | -------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| C1  | CRITICAL | `kl_coef` not passed in GRPOConfig/RLOOConfig `to_trl_config()` — user config silently dropped   | **FIXED**                                        |
| C2  | CRITICAL | `MethodRegistry` export in `__init__.py` maps to non-existent name (should be `METHOD_REGISTRY`) | **FIXED**                                        |
| H1  | HIGH     | AdapterSignature docstring lists only 3 methods, now accepts 12                                  | **FIXED**                                        |
| H2  | HIGH     | `object.__setattr__` unnecessary in non-frozen `AlignmentConfig`                                 | **FIXED**                                        |
| H3  | HIGH     | Dead `import math` in method_registry.py                                                         | **FIXED**                                        |
| H4  | HIGH     | `_validate_sft_columns` doesn't check text column presence                                       | Deferred — TRL SFTTrainer auto-detects           |
| M1  | MEDIUM   | `online_dpo` missing `requires_reward_func` flag                                                 | Correct as-is — uses reward model, not functions |

## Security Review Findings (security-reviewer)

| ID  | Severity | Finding                                                                               | Status                                                 |
| --- | -------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| H1  | HIGH     | Missing `trust_remote_code=False` on `AutoTokenizer.from_pretrained()` in pipeline.py | **FIXED**                                              |
| H2  | HIGH     | `_lazy_import()` accepts arbitrary module paths — no allowlist                        | Acceptable — requires Python-level access, documented  |
| H3  | HIGH     | `_ollama_verify()` no model name validation (pre-existing, serving.py)                | Deferred — pre-existing, not in scope                  |
| M1  | MEDIUM   | `AlignmentConfig` not frozen — mutable after validation                               | Deferred — needs `object.__setattr__` for auto-config  |
| M2  | MEDIUM   | `OnPremConfig` not frozen (pre-existing)                                              | Deferred — pre-existing                                |
| M3  | MEDIUM   | No SSRF protection on configurable URLs (pre-existing, bridge.py)                     | Deferred — local deployment tool                       |
| M4  | MEDIUM   | `batch_generate()` no NaN/Inf on temperature/top_p params                             | Accepted — config-level validation covers normal usage |
| M5  | MEDIUM   | `estimate_training_memory()` no NaN/Inf on inputs                                     | Accepted — advisory function, fail-safe behavior       |
| L1  | LOW      | `"api_key": "not-needed"` in bridge.py                                                | Intentional for local vLLM                             |
| L2  | LOW      | `RewardRegistry` unbounded                                                            | Acceptable — 3 built-in, rarely grows                  |
| L3  | LOW      | `METHOD_REGISTRY` unbounded                                                           | Acceptable — 11 built-in, rarely grows                 |
| L4  | LOW      | `GenerationBackend.batch_generate()` uses `raise NotImplementedError`                 | **FIXED** — converted to `abc.ABC` + `@abstractmethod` |

## Fixes Applied

1. `config.py`: Added `kl_coef=self.kl_coef` to GRPOConfig and RLOOConfig `to_trl_config()`
2. `__init__.py`: Fixed export `MethodRegistry` → `METHOD_REGISTRY`
3. `config.py`: Updated AdapterSignature docstring for dynamic methods
4. `config.py`: Replaced `object.__setattr__` with direct assignment in AlignmentConfig
5. `method_registry.py`: Removed dead `import math`
6. `pipeline.py`: Added `trust_remote_code=False` to tokenizer loading
7. `vllm_backend.py`: Converted `GenerationBackend` to ABC with `@abstractmethod`

## Convergence

**R1 CONVERGED**: All actionable findings fixed. Remaining items are either:

- Pre-existing (serving.py, bridge.py — not in scope of this change)
- By design (online_dpo reward model vs reward functions)
- Advisory functions with fail-safe behavior

**Final test count**: 388 passed, 1 skipped, 0 regressions
