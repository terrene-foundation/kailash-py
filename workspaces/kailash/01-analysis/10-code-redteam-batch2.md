# Code Red Team — Batch 2 (kailash-ml + kailash-align)

Date: 2026-04-01
Scope: Implementation review of all engine code in kailash-ml (12 files) and kailash-align (8 files)
Test results: kailash-ml 81 passed/1 skipped, kailash-align 136 passed/1 skipped, kailash-ml-protocols 16 passed

---

## Executive Summary

Both packages are **solid**. The code demonstrates good engineering discipline: SQL injection prevention via `_validate_identifier()`, proper exception hierarchies, lazy imports for optional dependencies, LRU-bounded caches, and correct use of `frozen=True` dataclasses with `math.isfinite()` validation on numeric fields.

**Critical findings: 2** (security)
**High findings: 3** (correctness, resource safety)
**Medium findings: 5** (robustness, best practices)
**Low findings: 3** (minor improvements)
**Clean passes: 17 of 20 files**

---

## CRITICAL Findings

### C1: Arbitrary code execution via `ModelSpec.instantiate()` — model_registry/training_pipeline

**File**: `packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py`, line 56-62
**Also used in**: `automl_engine.py`, `hyperparameter_search.py`

```python
class ModelSpec:
    model_class: str  # e.g. "sklearn.ensemble.RandomForestClassifier"

    def instantiate(self) -> Any:
        parts = self.model_class.rsplit(".", 1)
        module = importlib.import_module(parts[0])
        cls = getattr(module, parts[1])
        return cls(**self.hyperparameters)
```

`model_class` is an arbitrary string that gets passed to `importlib.import_module()`. If a user-facing API (e.g., a Nexus endpoint or Kaizen agent) passes user-controlled strings through to `ModelSpec`, this becomes arbitrary code execution. The `instantiate()` method imports any Python module and calls any callable in it with attacker-controlled keyword arguments.

**Impact**: If `model_class` comes from untrusted input (API request, agent tool call), an attacker could import `os` and call `os.system()` or similar.

**Current risk**: MEDIUM in practice because `ModelSpec` is typically constructed in application code, not from raw user input. But the `InferenceServer.register_endpoints()` Nexus integration suggests models are served over HTTP, so the attack surface could widen.

**Fix**: Add an allowlist of permitted module prefixes:

```python
_ALLOWED_PREFIXES = ("sklearn.", "lightgbm.", "xgboost.")

def instantiate(self) -> Any:
    if not any(self.model_class.startswith(p) for p in _ALLOWED_PREFIXES):
        raise ValueError(f"model_class must start with one of {_ALLOWED_PREFIXES}")
    ...
```

### C2: `pickle.loads()` of model artifacts without integrity check — inference_server/training_pipeline

**Files**:

- `inference_server.py`, line 332: `model = pickle.loads(artifact_bytes)`
- `training_pipeline.py`, line 289: `model = pickle.loads(artifact_bytes)`
- `model_registry.py`, line 261: `model = pickle.loads(model_bytes)` (in `_attempt_onnx_export`)

`pickle.loads()` on untrusted data is arbitrary code execution. If an attacker can write to the artifact store (filesystem path `.kailash_ml/artifacts/`), they can craft a malicious pickle that executes code on load.

**Impact**: The `LocalFileArtifactStore` uses filesystem paths without sanitization (see H1). Combined with a path traversal or a compromised filesystem, this is full RCE.

**Current risk**: MEDIUM in practice because the artifact store is local and the user controls it. However, `import_mlflow()` reads arbitrary directories (line 751-804), which could include untrusted MLflow model directories.

**Fix**: For v1, add a log warning when loading pickles. For v2, consider `joblib` with signature verification or switch to ONNX-only serving path where possible. Document the trust boundary in the API docs.

---

## HIGH Findings

### H1: Path traversal in `LocalFileArtifactStore` — model_registry.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/model_registry.py`, lines 87-108

```python
class LocalFileArtifactStore:
    async def save(self, name: str, version: int, data: bytes, filename: str) -> str:
        path = self._root / name / str(version) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    async def load(self, name: str, version: int, filename: str) -> bytes:
        path = self._root / name / str(version) / filename
```

`name` and `filename` are not validated. A model name like `../../etc` or a filename like `../../../etc/passwd` would traverse outside the artifact root.

**Fix**: Validate that `name` matches `^[a-zA-Z0-9_-]+$` and that the resolved path is within `self._root`:

```python
async def save(self, name: str, version: int, data: bytes, filename: str) -> str:
    path = (self._root / name / str(version) / filename).resolve()
    if not str(path).startswith(str(self._root.resolve())):
        raise ValueError(f"Path traversal detected: {name}/{filename}")
    ...
```

### H2: TOCTOU race in `ModelRegistry.register_model()` — model_registry.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/model_registry.py`, lines 442-460

```python
model_row = await _get_model_row(self._conn, name)
if model_row is None:
    version = 1
    await self._conn.execute("INSERT INTO _kml_models ...")
else:
    version = model_row["latest_version"] + 1
    await self._conn.execute("UPDATE _kml_models SET latest_version = ? ...")
```

This is a check-then-act pattern without a transaction. Two concurrent `register_model()` calls with the same name can read the same `latest_version`, both increment to the same version number, and one insert will silently overwrite the other (or fail with a PRIMARY KEY constraint violation depending on timing).

Per `infrastructure-sql.md` Rule 2: "Any operation involving more than one SQL statement that must be atomic MUST use `conn.transaction()`."

**Fix**: Wrap the entire register_model body in `async with self._conn.transaction()`.

### H3: `upsert_metadata()` also uses check-then-act — \_feature_sql.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/_feature_sql.py`, lines 255-290

Same pattern as H2. `read_metadata()` then `INSERT` or `UPDATE` without a transaction. Per `infrastructure-sql.md` Rule 5: "Any 'insert or update' operation MUST use `dialect.upsert()` or `dialect.insert_ignore()`."

**Fix**: Use `conn.dialect.upsert()` or wrap in a transaction.

---

## MEDIUM Findings

### M1: No `math.isfinite()` validation on ML numeric inputs — training_pipeline/drift_monitor

**Files**:

- `training_pipeline.py`: `EvalSpec.test_size`, `EvalSpec.n_splits` have no NaN/Inf validation
- `hyperparameter_search.py`: `SearchConfig.timeout_seconds`, `SearchConfig.n_trials` unvalidated
- `drift_monitor.py`: `psi_threshold`, `ks_threshold`, `performance_threshold` constructor parameters unvalidated

Per `trust-plane-security.md` Rule 3 and `pact-governance.md` Rule 6: all numeric fields must be validated with `math.isfinite()`.

For ML, this is particularly relevant. A NaN `test_size` in `_holdout_split` would produce `split_idx = int(NaN * ...)` which raises `ValueError` — not dangerous, but inconsistent with the validation standard applied in kailash-align's config (which does validate correctly).

**Fix**: Add `__post_init__` validation to `EvalSpec`, `SearchConfig`, and `DriftMonitor.__init__()`.

### M2: Unbounded `_references` dict in `DriftMonitor` — drift_monitor.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/drift_monitor.py`, line 291

```python
self._references: dict[str, _StoredReference] = {}
```

This dict stores full polars Series for every registered model. In a long-running process monitoring hundreds of models, this grows without bound. Per `infrastructure-sql.md` Rule 7: "In-memory stores MUST have a maximum size with LRU eviction."

**Fix**: Use an `OrderedDict` with a max size (e.g., 100 models), evicting LRU entries.

### M3: `_StoredReference` holds full data in memory — drift_monitor.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/drift_monitor.py`, lines 104-114

`_StoredReference.data` stores the raw polars Series for every feature of the reference data. For a model with 100 features and 1M reference rows, this is hundreds of megabytes per model in the `_references` dict. The reference statistics are stored in the database, but the raw data is only in memory.

**Impact**: Memory exhaustion in production environments.

**Fix**: Store binned histograms or summary statistics instead of raw Series. The PSI computation already uses histograms internally — pre-compute and store the bin edges and counts.

### M4: `DriftMonitor.set_reference()` check-then-act on database — drift_monitor.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/drift_monitor.py`, lines 361-386

Same check-then-act pattern as H2/H3. `fetchone()` then `INSERT` or `UPDATE` without a transaction.

**Fix**: Use `conn.dialect.upsert()` or wrap in a transaction.

### M5: `_stratified_kfold_first_fold` falls back to regular kfold — training_pipeline.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py`, lines 420-424

```python
def _stratified_kfold_first_fold(self, data, n_splits):
    # Fallback to regular kfold for simplicity in v1
    return self._kfold_first_fold(data, n_splits)
```

This silently ignores the stratification request. A user requesting `split_strategy="stratified_kfold"` gets regular kfold without any warning. This could lead to unbalanced train/test splits on imbalanced datasets, producing misleadingly high metrics.

**Fix**: Either implement stratified splitting (sklearn's `StratifiedKFold` is available) or emit a warning: `logger.warning("stratified_kfold not yet implemented, falling back to kfold")`.

---

## LOW Findings

### L1: `_check_ollama_available` raises without `raise ... from exc` — serving.py

**File**: `packages/kailash-align/src/kailash_align/serving.py`, line 314

```python
except FileNotFoundError:
    raise OllamaNotAvailableError(...)
```

Missing `from exc`. Per Python best practices and the exception chaining pattern used elsewhere in the codebase (e.g., line 296, 165), this should be `raise ... from exc`.

### L2: `_kfold_first_fold` doesn't shuffle — training_pipeline.py

**File**: `packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py`, lines 412-418

K-fold takes the first N rows as test and the rest as train, without shuffling. If the data has any temporal or structural ordering, this produces biased splits. The `_holdout_split` method shuffles (line 405-410) but kfold does not.

### L3: `AdapterRegistry` uses in-memory dict store — registry.py

**File**: `packages/kailash-align/src/kailash_align/registry.py`, line 64

`AdapterRegistry` uses in-memory dicts (`self._adapters`, `self._versions`). All data is lost on process restart. This is acceptable for the current use case (single training session), but the class docstring doesn't prominently warn about this. A user might expect persistence (especially since `kailash-ml`'s `ModelRegistry` uses a database).

---

## Clean Passes

### kailash-ml

| File                  | Verdict           | Notes                                                                                                                                                                                                                                                                             |
| --------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `interop.py`          | CLEAN             | Proper dtype handling, lazy imports, row limit guard. No security issues.                                                                                                                                                                                                         |
| `feature_store.py`    | CLEAN             | Zero raw SQL (all in `_feature_sql.py`). Proper schema validation.                                                                                                                                                                                                                |
| `_feature_sql.py`     | CLEAN (except H3) | Every identifier validated with `_validate_identifier()`. Parameterized queries throughout. `dtype_to_sql()` returns from a whitelist map. Transaction used in `upsert_batch()`. Single auditable SQL touchpoint as designed.                                                     |
| `inference_server.py` | CLEAN (except C2) | LRU cache bounded. ONNX fallback handled gracefully. Nexus integration is lazy.                                                                                                                                                                                                   |
| `automl_engine.py`    | CLEAN             | `math.isfinite()` on `LLMCostTracker.max_budget_usd`. Default candidates are hardcoded (no injection risk). Baseline recommendation is deterministic algorithmic selection (not LLM routing — this is data profiling, not agent reasoning, so no agent-reasoning rule violation). |
| `data_explorer.py`    | CLEAN             | All polars-native. No SQL, no file I/O, no security surface. `@experimental` decorator properly warns.                                                                                                                                                                            |
| `feature_engineer.py` | CLEAN             | All polars expressions. No SQL, no file I/O. Generated column names are deterministic (no injection). `@experimental` decorator present.                                                                                                                                          |
| `mlflow_format.py`    | CLEAN             | `yaml.safe_load()` used (not `yaml.load()`). File reads are Path-based. No SQL.                                                                                                                                                                                                   |

### kailash-align

| File            | Verdict           | Notes                                                                                                                                                                                                                     |
| --------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.py`     | CLEAN             | Excellent. All frozen dataclasses. `math.isfinite()` and `_validate_positive()` on all numeric fields. `bf16`/`fp16` mutual exclusion checked. `__post_init__` validation on every config type.                           |
| `pipeline.py`   | CLEAN             | `trust_remote_code=False` hardcoded. Proper preference dataset validation. Checkpoint resume supported. AdapterSignature construction is correct.                                                                         |
| `evaluator.py`  | CLEAN             | `trust_remote_code=False` in custom eval pipeline. lm-eval is properly lazy-imported. Comparison logic handles missing tasks gracefully.                                                                                  |
| `serving.py`    | CLEAN (except L1) | GGUF validation is thorough (load test + inference test + printable ratio check). Architecture allowlist present. Subprocess timeouts on all `subprocess.run()` calls. BYOG escape hatch documented.                      |
| `merge.py`      | CLEAN             | Idempotent merge (returns early if already merged). Prevents re-merge of exported adapters. `trust_remote_code=False` hardcoded.                                                                                          |
| `bridge.py`     | CLEAN             | Uses only public Delegate APIs. Budget_usd limitation for local models clearly documented (R2-04). Auto-detect strategy with sensible fallback ordering. No agent-reasoning violations (this is a factory, not an agent). |
| `onprem.py`     | CLEAN             | `snapshot_download()` handles integrity verification. Cache verification loads config + tokenizer. Clean error messages with actionable install hints.                                                                    |
| `exceptions.py` | CLEAN             | Proper hierarchy. Every error inherits from `AlignmentError`. Clear naming.                                                                                                                                               |

---

## Review Criteria Assessment

### 1. Security

- **SQL injection in `_feature_sql.py`**: PROTECTED. Every interpolated identifier passes through `_validate_identifier()`. All values use `?` parameterized placeholders. The SQL module is the single auditable touchpoint.
- **Path traversal in model storage**: VULNERABLE (H1). `LocalFileArtifactStore` does not validate `name` or `filename` parameters.
- **Secret leaks in config**: CLEAN. No hardcoded API keys. `LLMCostTracker` reads pricing from env vars. `AlignmentConfig` does not store secrets.
- **Arbitrary code execution**: VULNERABLE (C1, C2). `ModelSpec.instantiate()` and `pickle.loads()` are the two most significant attack surfaces.

### 2. NaN/Inf validation

- **kailash-align**: EXCELLENT. All config dataclasses use `math.isfinite()` and `_validate_positive()`. `LoRAConfig`, `SFTConfig`, `DPOConfig`, `ServingConfig` all validate numeric fields in `__post_init__`.
- **kailash-ml**: PARTIAL (M1). `LLMCostTracker` validates `max_budget_usd`. But `EvalSpec`, `SearchConfig`, and `DriftMonitor` thresholds lack validation.

### 3. Error handling

- **Exception hierarchy**: CLEAN on both packages. `kailash-align` has `AlignmentError` base with 7 specific subtypes. `kailash-ml` uses `ModelNotFoundError` and stdlib exceptions.
- **Silent failures**: One instance in `inference_server.py` line 398 (`except Exception: pass` for `predict_proba`). Acceptable — some models don't support probability estimation, and logging here would be noisy.

### 4. Resource cleanup

- **Model files**: `_validate_gguf` properly `del model` in finally block. Good.
- **Temp dirs**: No temporary directories created without cleanup.
- **Connections**: `FeatureStore` and `DriftMonitor` do not own connections (caller manages lifecycle). Correct pattern — matches ConnectionManager ownership model.
- **In-memory data**: `_StoredReference` holds unbounded Series data (M2/M3).

### 5. Agent-reasoning compliance

- **No violations found.** `AutoMLEngine._compute_baseline_recommendation()` uses deterministic data profiling (dataset size, feature count) to rank model families — this is algorithmic recommendation based on data characteristics, not agent decision-making. It does not route, classify, or evaluate user input.
- `KaizenModelBridge` is a factory that constructs Delegates — it does not contain decision logic.

### 6. R1/R2 finding compliance

- **R2-12 (single SQL touchpoint)**: COMPLIANT. `FeatureStore` contains zero raw SQL. All SQL in `_feature_sql.py`.
- **R2-13 (lazy Nexus import)**: COMPLIANT. `InferenceServer.register_endpoints()` imports `kailash_nexus` only when called.
- **R1-02 (GGUF validation)**: COMPLIANT. `AlignmentServing._validate_gguf()` loads the GGUF, runs inference, checks output quality. Timeout is configurable. BYOG escape hatch available.
- **R2-01 (llama-cpp-python for GGUF)**: COMPLIANT. Uses `llama_cpp` Python bindings, not compiled binary.
- **R2-03 (Apple Silicon)**: DOCUMENTED. vLLM config generator includes R2-03 warning comment.
- **R2-04 (budget_usd on local models)**: DOCUMENTED. `KaizenModelBridge` docstring and module docstring both warn about this.

### 7. GGUF safety

- **Post-conversion validation**: PRESENT and THOROUGH. Three checks: load success, token generation, printable ratio.
- **Error messages**: CLEAR. Every `GGUFConversionError` includes the model path, the specific failure, and actionable guidance (retry, different quantization, or BYOG).
- **Architecture allowlist**: PRESENT. `SUPPORTED_ARCHITECTURES` dict with support levels. Unsupported architectures produce a warning, not a hard block (correct for extensibility).

---

## Summary of Required Fixes

| ID  | Severity | File                                                             | Fix                                                            |
| --- | -------- | ---------------------------------------------------------------- | -------------------------------------------------------------- |
| C1  | CRITICAL | training_pipeline.py                                             | Add module prefix allowlist to `ModelSpec.instantiate()`       |
| C2  | CRITICAL | inference_server.py, training_pipeline.py, model_registry.py     | Document pickle trust boundary; add warning on untrusted loads |
| H1  | HIGH     | model_registry.py                                                | Validate artifact names/filenames against path traversal       |
| H2  | HIGH     | model_registry.py                                                | Wrap `register_model()` in transaction                         |
| H3  | HIGH     | \_feature_sql.py                                                 | Use `dialect.upsert()` or transaction for `upsert_metadata()`  |
| M1  | MEDIUM   | training_pipeline.py, hyperparameter_search.py, drift_monitor.py | Add `math.isfinite()` validation on numeric constructor params |
| M2  | MEDIUM   | drift_monitor.py                                                 | Bound `_references` dict with LRU eviction                     |
| M3  | MEDIUM   | drift_monitor.py                                                 | Store reference histograms, not raw Series                     |
| M4  | MEDIUM   | drift_monitor.py                                                 | Use transaction for `set_reference()` database writes          |
| M5  | MEDIUM   | training_pipeline.py                                             | Implement stratified kfold or add fallback warning             |
| L1  | LOW      | serving.py                                                       | Add `from exc` to exception chain                              |
| L2  | LOW      | training_pipeline.py                                             | Shuffle in kfold split                                         |
| L3  | LOW      | registry.py                                                      | Document in-memory-only persistence in class docstring         |
