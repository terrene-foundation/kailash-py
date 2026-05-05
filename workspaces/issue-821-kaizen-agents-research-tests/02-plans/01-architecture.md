# Architecture Plan — Issue #821

## Summary

Re-establish unit-test parity for the three modules under
`packages/kaizen-agents/src/kaizen_agents/research_patterns/`. Three Tier-1
test files at the new home, exercising construction + canonical methods.
Single shard (load-bearing logic budget is well under the per-shard cap;
test code, not production logic).

## Source surface (verified by reading 2026-05-05)

### `advanced_patterns.py` (347 LOC)

| Symbol                             | Shape                                                                                                                    | Canonical methods                                                                                                                                                                                               |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PatternStrategy` (Enum)           | `SEQUENTIAL`, `PARALLEL`, `ENSEMBLE`                                                                                     | —                                                                                                                                                                                                               |
| `AdaptationStrategy` (Enum)        | `PERFORMANCE_BASED`, `ACCURACY_BASED`, `FAULT_TOLERANT`                                                                  | —                                                                                                                                                                                                               |
| `LearningStrategy` (Enum)          | `BANDIT`, `GRADIENT`                                                                                                     | —                                                                                                                                                                                                               |
| `CompositionalPattern` (dataclass) | `features: List[str]`, `strategy: str`, `num_components` (auto)                                                          | `execute(input_data)` dispatches to `_execute_sequential` / `_execute_parallel` / `_execute_ensemble`                                                                                                           |
| `HierarchicalPattern` (dataclass)  | `levels: List[List[str]]`, `num_levels` (auto)                                                                           | `get_level_features(level)`, `execute(input_data)`                                                                                                                                                              |
| `AdaptivePattern` (dataclass)      | `base_features`, `adaptation_strategy`, `can_adapt`, `adaptation_history`, `performance_stats`                           | `execute(input_data)`, `_select_feature()`, `get_adaptation_history()`                                                                                                                                          |
| `MetaLearningPattern` (dataclass)  | `candidate_features`, `learning_strategy`, `exploration_rate`, `execution_history`, `feature_weights`, `feature_rewards` | `execute(input_data)`, `provide_feedback(exec_id, reward)`, `get_learning_stats()`, `get_feature_weights()`                                                                                                     |
| `AdvancedPatternBuilder` (class)   | `__init__(registry=None, feature_manager=None)`                                                                          | `compose(features, strategy)`, `hierarchical(levels)`, `adaptive(base_features, adaptation_strategy)`, `meta_learning(candidate_features, learning_strategy, exploration_rate=0.1)`, `get_available_features()` |

### `experimental.py` (231 LOC)

| Symbol                            | Shape                                                                                                               | Canonical methods                                                                                                |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `ExperimentalFeature` (dataclass) | 9 fields incl. `paper: ResearchPaper`, `validation: ValidationResult`, `signature_class: Type[Signature]`, `status` | `is_enabled()`, `enable()`, `disable()`, `execute(**kwargs)`, `update_status(new_status)`, `get_documentation()` |

Lifecycle invariants (per docstring):

- `experimental → beta`, `beta → stable`, `any → deprecated` permitted
- `experimental → stable`, `stable → experimental`, `beta → experimental` raise `ValueError`
- `execute()` raises `RuntimeError` when `is_enabled()` is False

External imports: `kaizen.research.parser.ResearchPaper`,
`kaizen.research.validator.ValidationResult`, `kaizen.signatures.Signature`
(verified signatures: `ResearchPaper(arxiv_id, title, authors, abstract,
methodology, metrics={}, code_url='', pdf_url='')`,
`ValidationResult(validation_passed, reproducibility_score, ...)`).

### `intelligent_optimizer.py` (206 LOC)

| Symbol                           | Shape                                                                                                                                                                           | Canonical methods                                                                                                                                                                                             |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OptimizationResult` (dataclass) | `best_params`, `improvement`, `iterations`                                                                                                                                      | —                                                                                                                                                                                                             |
| `IntelligentOptimizer` (class)   | `__init__(strategy, acquisition='ei', population_size=20, crossover_rate=0.8, mutation_rate=0.1, epsilon=0.1, objectives=None, weights=None)` + RL state (`policy`, `q_values`) | `optimize(feature_id, parameter_space, n_iterations=10, n_generations=10)` dispatches `bayesian` / `genetic` / `multi_objective`; RL: `select_action(state)`, `update_policy(action, reward)`, `get_policy()` |

## Test architecture

### Layout

```
packages/kaizen-agents/tests/unit/research_patterns/
├── __init__.py             (empty package marker)
├── test_advanced_patterns.py
├── test_experimental.py
└── test_intelligent_optimizer.py
```

Mirrors the existing `packages/kaizen-agents/tests/unit/` layout (peers:
`agents/`, `api/`, `governance/`, etc., each a sub-package of unit tests).

### Tier and conventions

- **Tier 1 (unit)** — `rules/testing.md`. Pure logic, no DB / no API / no
  network. Mocks permitted (we don't need any — modules are self-contained
  with stdlib-only deps for their canonical paths).
- Helper classes for `experimental.py` (a fake `Signature` subclass) MUST
  use `*Stub` / `*Helper` / `*Fake` suffix per `rules/testing.md`. The
  signature class needs an `execute()` method that the
  `ExperimentalFeature.execute()` path will invoke.
- Determinism: `IntelligentOptimizer` and `MetaLearningPattern` /
  `AdaptivePattern` use `random.random()`, `random.choice()`,
  `random.uniform()`, `random.randint()`. Tests MUST seed `random.seed(...)`
  in fixtures or per-test to keep assertions deterministic. The `execute()`
  paths of compositional/hierarchical patterns are deterministic by
  construction.
- File-naming: `test_<module_basename>.py` matches the existing layout.
- Marker: no `@pytest.mark.unit` — kaizen-agents tests are uniformly
  collected without per-tier markers (verified by spot-check of
  `tests/unit/test_types.py` — no marker).

### Coverage targets per AC

| AC  | Test file                       | Symbols + methods exercised                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| --- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | `test_advanced_patterns.py`     | `AdvancedPatternBuilder.__init__` / `.compose` / `.hierarchical` / `.adaptive` / `.meta_learning` / `.get_available_features`; `CompositionalPattern.execute` (3 strategy branches); `HierarchicalPattern.execute` + `.get_level_features`; `AdaptivePattern.execute` + `.get_adaptation_history` (3 strategy branches); `MetaLearningPattern.execute` + `.provide_feedback` + `.get_learning_stats` + `.get_feature_weights` (2 learning-strategy branches) |
| 2   | `test_experimental.py`          | `ExperimentalFeature` construction; `is_enabled` initial-False; `enable` / `disable`; `execute` raises `RuntimeError` when disabled; `execute(**kwargs)` calls signature.execute when enabled; `update_status` valid + invalid transitions; `get_documentation` returns markdown containing key fields                                                                                                                                                       |
| 3   | `test_intelligent_optimizer.py` | `OptimizationResult` construction; `IntelligentOptimizer.__init__` defaults + overrides; `optimize` dispatch on `bayesian` / `genetic` / `multi_objective` returns expected shape; unknown strategy returns `{}`; `select_action` exploration + exploitation paths (seeded); `update_policy` + `get_policy`; `_dominates` predicate                                                                                                                          |
| 4   | (all three)                     | `pytest --collect-only -q packages/kaizen-agents/tests/unit/research_patterns/` exits 0; full collect across `packages/kaizen-agents/tests/` exits 0                                                                                                                                                                                                                                                                                                         |

Implicit AC (tests pass): `pytest packages/kaizen-agents/tests/unit/research_patterns/` exits 0.

### Estimated LOC

- `test_advanced_patterns.py`: ~250–330 LOC (5 classes × ~5 tests each, plus enum smoke)
- `test_experimental.py`: ~120–160 LOC (1 class, ~10 tests; lifecycle table + signature stub)
- `test_intelligent_optimizer.py`: ~150–200 LOC (1 class, dispatch + RL methods)

Total ~520–690 LOC of test code. Test code does NOT count toward the
load-bearing logic budget per `rules/autonomous-execution.md` — single
shard is well within capacity.

## Brief corrections

None. The brief's claims:

- 3 modules at the named paths — verified.
- Names of classes per AC — all present in source as listed.
- `pytest --collect-only` AC interpretable as written.
- `~1500 LOC` claim slightly high (actual: 347 + 231 + 206 = 784 LOC of
  source). Does not change scope.

## Risks

1. `experimental.py` depends on `kaizen.research.parser` /
   `kaizen.research.validator` / `kaizen.signatures` from the kailash-kaizen
   package. Those modules MUST be importable at test collection time.
   Verified: `packages/kailash-kaizen/src/kaizen/research/{parser,validator}.py`
   exist and define the imported names with the expected signatures.
2. `random`-based assertions could become flaky without seeding. Mitigation:
   seed at fixture or per-test scope.
3. Adding `tests/unit/research_patterns/__init__.py` follows existing
   sub-package convention; spot-checked `tests/unit/agents/__init__.py`
   exists in the same shape.

## Out of scope

- Tier 2/3 integration coverage for these modules (only Tier-1 parity asked).
- Touching `research_patterns/*` source — surface stays as-is.
- Issue #822 cascade.
- Pre-existing `uv.lock` modifications.

## Gate to /todos

Plan ready. Single shard. Hand off to `/todos` for human approval gate.
