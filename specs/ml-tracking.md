# Kailash ML Tracking — Experiment Tracker, Model Registry, Artifact Store

Version: 2.0.0 (draft)
Package: `kailash-ml`
Parent domain: ML Lifecycle (`ml-engines.md` covers training; `ml-features.md` covers feature storage (future); `ml-drift.md` covers drift detection (future))
Scope authority: `ExperimentTracker`, `ModelRegistry`, `ArtifactStore`, their interop, their MCP surface, multi-tenant storage, retention, migration

Status: DRAFT — authored at `workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md`. Becomes `specs/ml-tracking.md` after human review. Supersedes the tracking sections of `ml-engines.md §1.2 (ModelRegistry)` and `§1.6 (ExperimentTracker)` when the 2.0 redesign lands.

Origin: `workspaces/kailash-ml-audit/analysis/00-synthesis-redesign-proposal.md` §2 (vision), §3.3 (MLflow parity gaps), §5 (API), §6.7 (PyCaret/MLflow-better claims).

---

## 1. Scope

### 1.1 In Scope

This spec is authoritative for:

- **Experiment runs** — lifecycle, nesting, metadata capture, metrics, parameters, tags, environment, auto-logging
- **Run metadata** — start/end time, host, Python/CUDA/Lightning versions, git SHA, device, accelerator, precision, tracker run_id
- **Model registry** — model names, integer-monotonic versions, aliases (`production`, `staging`, `champion`, etc.), stages (legacy compatibility), signatures, lineage
- **Artifact storage** — content-addressed blob storage, multiple backends (`file://`, `sqlite://`, `s3://`, `gs://`, `azure://`, `http(s)://`), SHA-256 dedupe, encryption at rest, retention policies
- **MCP surface** — tools exposed via `kailash-mcp` framework for agent-driven experiment introspection and run comparison
- **Multi-tenant storage** — tenant-scoped storage key shapes, `TenantRequiredError` semantics, tenant-aware invalidation
- **Retention and GDPR** — per-alias retention windows, data-subject erasure, audit-trail of erasure
- **Migration** — bulk import from MLflow servers (runs, experiments, models, artifacts)
- **In-memory mode** — `sqlite+memory` store for notebook workflows with no persistence
- **Cross-SDK alignment** — shared contract between kailash-py and kailash-rs, with per-language backend notes

### 1.2 Out of Scope

- **Training itself** — `ml-engines.md` owns the `Engine`, `Trainable` protocol, backend matrix, Lightning integration, ONNX export path. This spec consumes training outputs via `log_model` / `register` and records the lineage.
- **Feature storage** — the future `ml-features.md` owns `FeatureStore`, point-in-time correctness, schema evolution. This spec references a feature store version as part of lineage but does not define its shape.
- **Drift detection** — the future `ml-drift.md` owns `DriftMonitor`, PSI/KS computation, drift reports. This spec records drift-report run_ids as child runs but does not define drift semantics.
- **Model serving** — `ml-engines.md §InferenceServer` owns `engine.serve()` and prediction endpoints. This spec records which model version is served via `alias="production"` but does not define the serving contract.
- **Alignment / LLM fine-tuning** — `alignment-training.md` and `alignment-serving.md` own those flows. Tracking integration points are at the alignment spec, not here.

---

## 2. `ExperimentTracker` Async-Context Contract

### 2.1 Construction

**MUST**: `ExperimentTracker` instances MUST be constructed via one of two entry points:

```python
# DO — convenience entry point
import kailash_ml as km
async with km.track(
    name="cart-abandonment-v3",
    tags={"env": "staging", "team": "growth"},
    tenant_id="acme",
    store="postgresql://...",
) as tracker:
    ...

# DO — explicit construction
from kailash_ml import ExperimentTracker
tracker = await ExperimentTracker.open(
    name="cart-abandonment-v3",
    tenant_id="acme",
    store="postgresql://...",
)
try:
    ...
finally:
    await tracker.close()

# DO NOT — synchronous construction with manual lifecycle
tracker = ExperimentTracker(conn, name="exp")  # BLOCKED — bypasses async context, leaks connection
```

**Why:** The async context manager is the only construction path that guarantees connection lifecycle, run auto-completion, and flush-on-exit. Direct constructors leak the database connection and leave runs in `RUNNING` state forever.

**BLOCKED rationalizations:**

- "I only need to log one metric, context manager is overkill"
- "The existing ExperimentTracker constructor works fine"
- "We can flush manually at the end of the script"

### 2.2 Async Context Manager Contract

**MUST**: `ExperimentTracker` MUST implement `__aenter__` / `__aexit__` and auto-close the active run with status:

- `COMPLETED` if the block exits normally
- `FAILED` if the block raises any exception (the exception MUST be re-raised, not swallowed — `except: pass` on `__aexit__` is BLOCKED per `rules/zero-tolerance.md` Rule 3)
- `KILLED` if `asyncio.CancelledError` bubbles through

```python
# DO — exceptions re-raise, status auto-set
async with km.track("exp") as t:
    await t.log_metric("accuracy", 0.91)
    raise RuntimeError("training diverged")
# tracker recorded status=FAILED, error_type=RuntimeError, error_msg="training diverged"
# exception propagates to caller

# DO NOT — silent swallow on __aexit__
async def __aexit__(self, exc_type, exc, tb):
    await self._end_run(status="FAILED" if exc else "COMPLETED")
    return True  # BLOCKED — suppresses exception
```

**Why:** Context managers that swallow exceptions hide training failures as "completed runs," and the next session's leaderboard shows a diverged model as the best candidate. Status must reflect reality.

### 2.3 Nested Runs

**MUST**: `tracker.run(name=, tags=)` MUST return an async context manager that creates a child run whose `parent_run_id` is the enclosing run. Nesting depth is unbounded.

```python
# DO — nested child runs
async with km.track("automl-sweep") as parent:
    await parent.log_param("strategy", "bayesian")
    for trial in trials:
        async with parent.run(name=f"trial-{trial.n}") as child:
            await child.log_param("lr", trial.lr)
            await child.log_metric("val_loss", trial.loss)

# DO NOT — sibling runs used to represent trials
for trial in trials:
    async with km.track(f"automl-sweep-trial-{trial.n}") as t:
        ...  # BLOCKED — no parent link, search_runs(parent_run_id=...) returns nothing
```

**Why:** Parent/child linkage is the structural substrate for HP search, AutoML, and fine-tuning lineage. Without it, comparing trial-level metrics requires grep-parsing run names, which defeats the query API.

### 2.4 Mandatory Auto-Capture

**MUST**: On run start, the tracker MUST capture the following fields without explicit user action. Missing any field is a HIGH finding in `/redteam`:

| Field                      | Source                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `start_time`               | `datetime.now(UTC)` at `__aenter__`                                                                          |
| `end_time`                 | `datetime.now(UTC)` at `__aexit__`                                                                           |
| `host`                     | `socket.gethostname()`                                                                                       |
| `python_version`           | `sys.version_info` triple                                                                                    |
| `kailash_ml_version`       | `kailash_ml.__version__`                                                                                     |
| `lightning_version`        | `lightning.pytorch.__version__` (if importable)                                                              |
| `torch_version`            | `torch.__version__` (if importable)                                                                          |
| `cuda_version`             | `torch.version.cuda` (if torch and CUDA present)                                                             |
| `git_sha`                  | `subprocess.run(["git", "rev-parse", "HEAD"])` if in a repo, else `None`. Failure logged, not raised.        |
| `git_dirty`                | `True` if `git status --porcelain` is non-empty                                                              |
| `device_used`              | From attached `TrainingResult.device_used` when `log_model(training_result=...)` is called                   |
| `accelerator`              | From `TrainingResult.accelerator`                                                                            |
| `precision`                | From `TrainingResult.precision`                                                                              |
| `tenant_id`                | From constructor / `km.track(tenant_id=)` or raises `TenantRequiredError` when multi-tenant mode             |

**Why:** Every reproducibility failure in the field traces to missing one of these fields. MLflow makes the Python / CUDA / device fields optional and the top-N rule of thumb is that 1 in 20 runs reproduced by another person fails because of environment drift that would have been captured here.

### 2.5 Logging Primitives

**MUST**: Each primitive has the listed signature. Polars-first return types apply where queries return tabular data.

```python
async def log_metric(
    self,
    key: str,
    value: float,
    *,
    step: Optional[int] = None,
    timestamp: Optional[datetime] = None,
) -> None: ...

async def log_metrics(self, metrics: Mapping[str, float], *, step: Optional[int] = None) -> None: ...

async def log_param(self, key: str, value: Any) -> None: ...

async def log_params(self, params: Mapping[str, Any]) -> None: ...

async def log_artifact(
    self,
    path: Union[str, Path, bytes],
    *,
    kind: str = "file",              # "file" | "directory" | "figure" | "table" | "model"
    name: Optional[str] = None,      # Display name; defaults to basename
    encryption: Optional[str] = None, # Override store default; None uses backend policy
) -> ArtifactHandle: ...

async def log_model(
    self,
    model: Any,
    *,
    format: str = "onnx",            # "onnx" (default) | "pickle" | "torch" | "lightning" | "sklearn"
    name: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    signature: Optional[ModelSignature] = None,
    lineage: Optional[Mapping[str, Any]] = None,
    training_result: Optional[TrainingResult] = None,  # Auto-populates device/accelerator/precision
) -> ModelVersionInfo: ...
```

**MUST**: `log_metric` values MUST be finite floats. `NaN`, `inf`, and `-inf` MUST raise `ValueError`. Silent coercion to `None` or `0.0` is BLOCKED.

**Why:** Non-finite metrics poison every downstream aggregation (mean loss, best-so-far). MLflow accepts `NaN` silently and leaderboard ties against a NaN sort the NaN as "best" on some databases.

### 2.6 Query Primitives

**MUST**: `tracker.search(filter=, order_by=, limit=)` MUST return a `polars.DataFrame` (not pandas). Filter syntax accepts MLflow-compatible expressions (`"metrics.accuracy > 0.9"`, `"params.lr = 0.01"`, `"tags.env = 'prod'"`) plus the kailash-ml extension `"device_used LIKE 'cuda%'"`.

```python
# DO — polars result, MLflow-compatible filter
df = await tracker.search(
    filter="metrics.accuracy > 0.9 AND tags.env = 'prod'",
    order_by="metrics.accuracy DESC",
    limit=50,
)
assert isinstance(df, pl.DataFrame)

# DO NOT — pandas return
# BLOCKED: tracker.search returning pd.DataFrame contradicts kailash-ml polars-first contract
```

**Why:** MLflow returns pandas, which forces downstream users to pay the pandas import cost and pandas-to-polars conversion. Polars-native queries let the leaderboard flow directly into `polars.DataFrame.to_torch()` for GPU-side analysis.

### 2.7 Storage Backends

**MUST**: `ExperimentTracker.open(store=...)` MUST accept the following backend URIs:

| URI scheme         | Use case                                             | Notes                                                                                                   |
| ------------------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `sqlite:///:memory:` | Unit tests only — evicted on process exit           | Alias `sqlite+memory` accepted for readability                                                         |
| `sqlite+memory`    | Notebook workflows with no persistence               | **MUST** be supported — closes the user-reported pain point #8 in `00-synthesis-redesign-proposal.md §3.6` |
| `sqlite:///path/to/ml.db` | Local single-file store                        | Default when `store=None` in `km.track()` — resolves to `~/.kailash_ml/ml.db`                           |
| `postgresql://...` | Multi-user, multi-host, prod                         | Recommended for any shared team                                                                         |
| `mysql://...`      | Multi-user, multi-host, prod                         | Same contract as PostgreSQL                                                                             |

**MUST**: The default `store` when `km.track()` is called with no arguments MUST be `f"sqlite:///{Path.home() / '.kailash_ml' / 'ml.db'}"`. The directory MUST be created if absent. Creation failure MUST raise a typed `TrackerStoreInitError`, not fall back to `:memory:`.

**Why:** Silent fallback to `:memory:` loses every run as soon as the process exits, which is worse than failing at construction because the user thinks their runs are persisted.

---

## 3. `ModelRegistry`

### 3.1 Model Names

**MUST**: Model names MUST be unique within a `(tenant_id, name)` pair. Re-registering a new version under an existing name increments the version. Re-using a version number is BLOCKED — versions are integer-monotonic.

```python
# DO — monotonic versions
v1 = await registry.register(model, name="churn")   # version=1
v2 = await registry.register(model_v2, name="churn") # version=2
v3 = await registry.register(model_v3, name="churn") # version=3

# DO NOT — version reuse
await registry.register(model, name="churn", version=1)  # BLOCKED on second call
```

**Why:** Version reuse breaks every downstream system that caches by version — InferenceServer's LRU, the artifact store's content-addressed dedupe, audit trails that say "model:churn:v3 predicted X." Immutable versions are the only way a historical audit survives refactor.

### 3.2 Aliases

**MUST**: Aliases are **mutable pointers** to specific versions. `registry.set_alias(name=, alias=, version=)` repoints the alias without touching historical versions. Aliases are opaque strings — no enforced vocabulary.

```python
# DO — alias moves, versions immutable
await registry.set_alias(name="churn", alias="production", version=3)
await registry.set_alias(name="churn", alias="production", version=5)  # moves pointer
# version 3 still exists and is still retrievable by version number

# DO NOT — "promote" mutates version metadata
# BLOCKED: registry.promote_version(3, "production") that changes v3.stage = "production"
# (see §3.6 for legacy stage compatibility)
```

**Why:** MLflow's original stage system (None/Staging/Production/Archived) mutated version metadata, which meant "what was in production on April 5?" required reading audit logs. Aliases-as-pointers make that a trivial join. MLflow itself deprecated stages in favor of aliases in 2.9 — this spec skips the stage era entirely.

### 3.3 Reserved Alias Names

**MUST**: The aliases `production`, `staging`, `champion`, `challenger`, `canary`, and `shadow` MUST resolve with the following semantics when consumed by `engine.serve()` and the MCP surface:

| Alias        | Meaning                                                               | Retention default           |
| ------------ | --------------------------------------------------------------------- | --------------------------- |
| `production` | The live-traffic model                                                | Retain indefinitely         |
| `staging`    | Candidate for next promotion                                          | Retain last 10              |
| `champion`   | Current best-performing model (synonym for production in A/B context) | Retain indefinitely         |
| `challenger` | Candidate being evaluated against champion                            | Retain last 10              |
| `canary`     | Gradually rolled-out candidate                                        | Retain last 10              |
| `shadow`     | Receives mirrored traffic, no user-facing outputs                     | Retain last 10              |

**Why:** Mirror the semantics of production deployment tooling so platform teams can port their existing runbooks. Without reserved names, every team reinvents the same four aliases and the MCP tools can't render a meaningful status.

### 3.4 Signatures Are Mandatory

**MUST**: Every `ModelVersionInfo` MUST carry a non-null `ModelSignature`. Registration without a signature MUST raise `ModelSignatureRequiredError`.

```python
# DO — signature attached
signature = ModelSignature(
    inputs=[FeatureField("age", "float"), FeatureField("income", "float")],
    outputs=[FeatureField("churn_prob", "float")],
    feature_names=["age", "income"],
)
await registry.register(model, name="churn", signature=signature)

# DO NOT — implicit signature
await registry.register(model, name="churn")  # BLOCKED — ModelSignatureRequiredError
```

**Why:** MLflow signatures are optional and the overwhelming majority of MLflow-registered models in the wild ship without one. At serving time the absence of a signature means the first bad input (wrong dtype, wrong order) silently returns garbage predictions.

### 3.5 Lineage Is Mandatory

**MUST**: Every `ModelVersionInfo` MUST carry a non-null `lineage` dict with at least these keys:

| Key                    | Type                  | Purpose                                                                                |
| ---------------------- | --------------------- | -------------------------------------------------------------------------------------- |
| `tracker_run_id`       | `str`                 | The ExperimentTracker run that produced the model                                      |
| `parent_version`       | `Optional[int]`       | For fine-tuned or retrained models — the version this was derived from                 |
| `training_data_uri`    | `Optional[str]`       | Pointer to the training dataset (S3 path, SQL query ID, DataFlow model+version)         |
| `feature_store_version` | `Optional[str]`      | Schema version from the feature store (when the future `ml-features.md` lands)          |
| `base_model_uri`       | `Optional[str]`       | For LoRA/alignment: the base model used                                                |

Registration with missing `tracker_run_id` MUST raise `LineageRequiredError`.

```python
# DO — full lineage auto-populated from tracker
async with km.track("v3-retrain") as t:
    result = await engine.train(...)
    await registry.register(
        result.model,
        name="churn",
        signature=sig,
        # lineage auto-populated from t.run_id, result.training_data_uri
    )

# DO NOT — register without a tracker context
await registry.register(model, name="churn", signature=sig)  # BLOCKED — LineageRequiredError
```

**Why:** Every production debugging session starts with "which data was this model trained on?" If lineage is optional it is skipped, and the answer becomes a git-log archaeology session. Mandatory lineage makes the answer a 1-line SQL query.

**BLOCKED rationalizations:**

- "This is an experimental model, lineage overhead is overkill"
- "We'll add lineage before shipping to production"
- "The user asked for a simple API"

### 3.6 Legacy Stages (1.x Compatibility)

**MUST**: The 1.x stage vocabulary (`staging`, `shadow`, `production`, `archived`) MUST be accepted at `registry.register(stage=...)` and MUST auto-convert to setting the corresponding alias. The `stage` parameter is deprecated — a `DeprecationWarning` MUST be emitted.

```python
# 1.x call — accepted with DeprecationWarning
await registry.register(model, name="churn", stage="staging")
# Equivalent to:
await registry.register(model, name="churn")  # version N
await registry.set_alias(name="churn", alias="staging", version=N)
```

**Why:** Downstream consumers listed in `00-synthesis-redesign-proposal.md §7` (aegis / aether / kz-engage) use the 1.x stage API. Hard breakage defers their migration; silent acceptance plus a loud deprecation gives them a bounded migration window.

### 3.7 Query Methods

**MUST**: Registry MUST expose the following async query methods:

```python
async def list(
    self,
    *,
    name: Optional[str] = None,
    alias: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100,
) -> List[ModelVersionInfo]: ...

async def get(
    self,
    name: str,
    *,
    version: Optional[int] = None,
    alias: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> ModelVersionInfo: ...

async def compare(
    self,
    name: str,
    version_a: int,
    version_b: int,
    *,
    tenant_id: Optional[str] = None,
) -> RegistryComparison: ...

async def set_alias(
    self,
    *,
    name: str,
    alias: str,
    version: int,
    tenant_id: Optional[str] = None,
) -> None: ...

async def delete_alias(
    self,
    *,
    name: str,
    alias: str,
    tenant_id: Optional[str] = None,
) -> None: ...
```

**Why:** Exposing alias operations and version lookups through explicit methods (not overloaded `get_model`) makes the MCP tool schema tractable and prevents the "pass `version=` and `alias=` together, one wins silently" class of bugs.

---

## 4. `ArtifactStore`

### 4.1 Backends

**MUST**: `ArtifactStore` implementations MUST exist for each URI scheme below. `store.from_uri(uri)` is the factory:

| Scheme           | Class                     | Use case                                                                |
| ---------------- | ------------------------- | ----------------------------------------------------------------------- |
| `file://`        | `LocalFileArtifactStore`  | Single-host dev, CI                                                     |
| `sqlite://`      | `SqliteBlobArtifactStore` | Small artifacts (<10 MB), notebook-friendly, embedded with tracker DB   |
| `s3://`          | `S3ArtifactStore`         | AWS prod, requires `boto3`                                              |
| `gs://`          | `GCSArtifactStore`        | GCP prod, requires `google-cloud-storage`                               |
| `azure://`       | `AzureBlobArtifactStore`  | Azure prod, requires `azure-storage-blob`                               |
| `http://`, `https://` | `HTTPReadOnlyArtifactStore` | Read-only import path, used by MLflow migration                      |

**Why:** Each backend exists for a specific use case; missing `sqlite://` forces notebook users onto the filesystem and breaks in JupyterHub ephemeral containers. Explicit backend list prevents the "add custom backend" sprawl MLflow experienced.

### 4.2 Content-Addressed Storage

**MUST**: Every artifact MUST be stored under its SHA-256 content hash. Uploading the same bytes twice MUST NOT produce a second stored copy — the second `put` returns the existing handle.

```python
# DO — content-addressed dedupe
h1 = await store.put(b"model_bytes...")
h2 = await store.put(b"model_bytes...")
assert h1.sha256 == h2.sha256
assert h1.storage_uri == h2.storage_uri  # same underlying blob

# DO NOT — path-keyed with overwrite
# BLOCKED: store.put(path="artifacts/v3/model.onnx", data=bytes)  that overwrites
```

**Why:** AutoML sweeps serialize the same base model hundreds of times with different hyperparameters. Content-addressed storage cuts artifact storage cost by 80%+ in a typical sweep. MLflow stores each run's artifacts under the run_id, which duplicates every byte across every trial.

### 4.3 Encryption at Rest

**MUST**: When an `encryption` policy is configured for the store, writes MUST encrypt before the bytes leave the tracker process. Encryption failure (unavailable key, library missing, invalid ciphertext length) MUST abort the write and raise `ArtifactEncryptionError`. Silent plaintext fallback is BLOCKED.

```python
# DO — encryption failure aborts write
store = S3ArtifactStore(bucket="...", encryption="aes-256-gcm", key_id=kms_key_arn)
try:
    h = await store.put(payload)
except ArtifactEncryptionError as e:
    logger.error("artifact.encryption.failed", extra={"reason": e.reason})
    raise  # never silently ship plaintext

# DO NOT — fallback to plaintext when encryption key unavailable
if not key_available:
    logger.warning("encryption key missing; storing plaintext")  # BLOCKED
    await backend.put_raw(payload)
```

**Why:** The Phase 5.10 DataFlow audit (referenced in `rules/zero-tolerance.md` Rule 2 "Fake encryption") found a store that accepted an `encryption_key` parameter and stored plaintext. Operators believed data was encrypted. The same failure mode in ML artifact storage ships model weights (which may contain memorized training data) in plaintext. Abort-on-failure is the only contract that delivers what the operator asked for.

**BLOCKED rationalizations:**

- "KMS is down, we'll retry later — ship unencrypted for now"
- "The model weights aren't sensitive data"
- "We'll add encryption once the feature ships"

### 4.4 Size Limits

**MUST**: Each store backend MUST expose `max_artifact_bytes` configured at construction. Default values:

| Backend                  | Default `max_artifact_bytes` |
| ------------------------ | ---------------------------- |
| `SqliteBlobArtifactStore` | 10 MB                        |
| `LocalFileArtifactStore` | 10 GB                        |
| `S3ArtifactStore`        | 5 TB (S3 object limit)       |
| `GCSArtifactStore`       | 5 TB                         |
| `AzureBlobArtifactStore` | 200 GB                       |

Exceeding the limit MUST raise `ArtifactSizeExceededError` at `put()` time with the current size, limit, and a suggestion to reconfigure or switch backend.

**Why:** Silent multi-gigabyte writes into `SqliteBlobArtifactStore` corrupt the tracker DB. The limit plus typed error forces the user to make a backend choice consciously.

### 4.5 Retention Policies

**MUST**: `store.configure_retention(policy)` MUST accept a `RetentionPolicy` that maps aliases and unaliased runs to retention windows:

```python
policy = RetentionPolicy(
    by_alias={
        "production": RetainAll(),
        "champion": RetainAll(),
        "staging": RetainLastN(10),
        "challenger": RetainLastN(10),
        "canary": RetainLastN(10),
        "shadow": RetainLastN(10),
    },
    unaliased_runs=RetainFor(days=90),
    orphan_artifacts=RetainFor(days=30),
)
await store.configure_retention(policy)
```

**MUST**: Retention MUST be enforceable via `await store.apply_retention(dry_run: bool = False)` which returns a `RetentionReport` listing deleted artifacts, freed bytes, and preserved artifacts. Retention MUST never delete artifacts reachable via any alias, regardless of age.

**Why:** MLflow's retention story is "write a cron that deletes old runs" which is left as an exercise to the user. The result is petabyte-scale MLflow servers in the wild because nobody wrote the cron. An in-product policy shifts the default from "retain forever" to "retain with intent."

---

## 5. MCP Surface

### 5.1 Server

**MUST**: `ExperimentTracker` MUST expose an MCP server at `kailash_ml.tracker.mcp.TrackerMCPServer`. The server MUST be registered via the `kailash-mcp` framework per `rules/framework-first.md` — rolling a custom MCP server is BLOCKED.

```python
# DO — framework-first MCP
from kailash_ml.tracker.mcp import TrackerMCPServer
from kailash.mcp import serve_mcp

server = TrackerMCPServer(tracker=my_tracker, registry=my_registry)
await serve_mcp(server, transport="stdio")

# DO NOT — hand-rolled FastMCP
# BLOCKED: from fastmcp import FastMCP; mcp = FastMCP("tracker"); ...
```

**Why:** The `kailash-mcp` framework enforces auth, rate-limits, and audit logging that a hand-rolled server silently skips. Every MLflow-like system that ships a custom MCP endpoint ends up re-implementing auth 3 months later.

### 5.2 Tools

**MUST**: `TrackerMCPServer` MUST expose the following MCP tools. Each is an independently invocable method with a JSON schema documented in the server class:

| Tool name             | Purpose                                                                                 |
| --------------------- | --------------------------------------------------------------------------------------- |
| `list_experiments`    | `(tenant_id, filter_expr, limit)` → `List[ExperimentInfo]`                              |
| `get_run`             | `(run_id, tenant_id)` → full metadata + metrics + params + auto-captured environment    |
| `search_runs`         | `(query, order_by, limit, tenant_id)` → `List[RunInfo]`                                 |
| `get_model`           | `(name, alias_or_version, tenant_id)` → `ModelVersionInfo` with resolved artifact URIs  |
| `list_models`         | `(name_pattern, tenant_id)` → `List[ModelVersionInfo]`                                  |
| `diff_runs`           | `(run_a, run_b, tenant_id)` → `RunDiff` with per-key param/metric/env deltas            |
| `list_aliases`        | `(name, tenant_id)` → `Dict[alias, version]`                                            |
| `get_lineage`         | `(model_name, version, tenant_id)` → full lineage chain to training data               |

**Why:** These eight tools are the smallest surface that lets an agent answer "which model is in production, how does it compare to the staging candidate, and what data was each trained on?" — the core MLflow use case. `diff_runs` is the killer feature MLflow does not provide.

### 5.3 `diff_runs` Contract

**MUST**: `diff_runs(run_a, run_b)` MUST return a `RunDiff` with three sections:

```python
@dataclass
class RunDiff:
    params: Dict[str, ParamDelta]          # keys present in either run
    metrics: Dict[str, MetricDelta]        # keys present in either run; includes per-step diff if both logged steps
    environment: Dict[str, EnvDelta]       # python/cuda/lightning/git_sha/device/accelerator/precision
    summary: str                           # human-readable one-paragraph summary
```

**MUST**: `RunDiff` MUST highlight **high-impact deltas** with a typed flag: different `git_sha` AND different `cuda_version` AND >5% metric delta → flagged as "reproducibility risk." The flag MUST be emitted as a structured field, not a free-text note.

**Why:** Without a diff primitive, users copy-paste two `get_run` outputs into a spreadsheet. The reproducibility-risk flag catches the exact pattern that causes "we can't reproduce the staging result in production" — different CUDA versions with otherwise-identical params.

---

## 6. Storage Key Shape

### 6.1 Tenant-Scoped Keys

**MUST**: All primary keys MUST follow the shape `kailash_ml:v1:{tenant_id}:{resource}:{id}`:

| Resource     | Key shape                                                |
| ------------ | -------------------------------------------------------- |
| Experiments  | `kailash_ml:v1:{tenant_id}:exp:{experiment_id}`          |
| Runs         | `kailash_ml:v1:{tenant_id}:run:{run_id}`                 |
| Models       | `kailash_ml:v1:{tenant_id}:model:{name}:{version}`       |
| Aliases      | `kailash_ml:v1:{tenant_id}:alias:{name}:{alias}`         |
| Artifacts    | `kailash_ml:v1:{tenant_id}:artifact:{sha256}`            |
| Lineage      | `kailash_ml:v1:{tenant_id}:lineage:{model}:{version}`    |

**Why:** Same tenant-dimension-everywhere contract as `rules/tenant-isolation.md` MUST Rule 1. Any piece of state without a tenant dimension leaks across tenants as soon as two tenants happen to share a primary key (run IDs are UUIDs but model names are user-chosen strings — overlap is the norm, not the exception).

### 6.2 Missing Tenant in Multi-Tenant Mode

**MUST**: When a `Tracker` or `Registry` is constructed with `multi_tenant=True`, every operation that constructs a key MUST require `tenant_id`. Missing `tenant_id` MUST raise `TenantRequiredError`. Silent fallback to `"default"` / `"global"` / `""` is BLOCKED.

```python
# DO — strict typed error
tracker = await ExperimentTracker.open(store=..., multi_tenant=True)
await tracker.log_metric("acc", 0.9)  # raises TenantRequiredError

# DO NOT — silent default
# BLOCKED: tenant_id = tenant_id or "default"
```

**Why:** Exact same failure mode as `rules/tenant-isolation.md` MUST Rule 2. The first day of multi-tenant ops looks fine because tenant A and tenant B happen not to share a run name. The incident surfaces months later when they do.

### 6.3 Invalidation

**MUST**: `tracker.invalidate_experiment(name, tenant_id)` and `registry.invalidate_model(name, tenant_id)` MUST accept `tenant_id` so that tenant-scoped invalidation does not blow away other tenants' cached slots. Unscoped invalidation is permitted ONLY with `tenant_id=None` explicitly passed, and the caller MUST demonstrate admin authority (see `security-auth.md`).

**Why:** See `rules/tenant-isolation.md` MUST Rule 3. A tenant password rotation should not trigger a registry cold-start for every other tenant.

### 6.4 Metric Labels

**MUST**: Prometheus metrics emitted by `ExperimentTracker` / `ModelRegistry` / `ArtifactStore` MUST NOT use `tenant_id` as an unbounded label. The bounded-top-N pattern from `rules/tenant-isolation.md` MUST Rule 4 applies — only the top 100 tenants get a label, the rest bucket as `"_other"`.

**Why:** See `rules/tenant-isolation.md` MUST Rule 4. A 10K-tenant SaaS producing 130K time series is a Prometheus OOM waiting to happen.

---

## 7. Retention and GDPR

### 7.1 Data Subject Columns

**MUST**: Every run, model, and artifact record MUST carry two fields:

| Field             | Type             | Purpose                                                                          |
| ----------------- | ---------------- | -------------------------------------------------------------------------------- |
| `owner_tenant_id` | `str`            | The tenant that owns the record (always populated)                               |
| `data_subject_ids` | `List[str]`     | Optional list of data subject IDs whose personal data may be present             |

Data subject IDs are typically user IDs, customer IDs, or patient IDs that appeared in the training data. Recording them is the caller's responsibility — `km.track(data_subject_ids=[...])` is the entry point.

**Why:** GDPR Article 17 (right to erasure) cannot be honored without knowing which runs / models / artifacts were trained on the subject's data. Optional fields get skipped in ad-hoc pipelines — the spec makes them a mandatory column with `List[str]` defaulting to `[]`.

### 7.2 Erasure API

**MUST**: `tracker.delete_data_subject(ids: List[str], *, reason: str, requested_by: str)` MUST:

1. Enumerate every run, model, and artifact whose `data_subject_ids` intersect `ids`
2. Delete the enumerated records atomically
3. Write an audit row per deletion to `_kml_erasure_audit` with `(record_id, record_type, data_subject_ids, reason, requested_by, timestamp)`
4. Return an `ErasureReport` listing deleted records and preserved-but-flagged records (models serving traffic under `alias=production`)

```python
# DO — audit trail persists even after records are gone
report = await tracker.delete_data_subject(
    ids=["user-42"],
    reason="GDPR Art. 17 request",
    requested_by="privacy-team@acme.com",
)
# The deleted runs' IDs are gone; _kml_erasure_audit has the audit trail

# DO NOT — erase without audit
# BLOCKED: raw DELETE WHERE user_id IN (...)  without writing _kml_erasure_audit
```

**MUST**: Records whose deletion would remove a model currently pointed at by `alias=production` MUST NOT be deleted. The `ErasureReport` MUST flag them with action `"requires_alias_migration"`. The caller is responsible for re-training on non-subject data and repointing the alias before retrying erasure.

**Why:** GDPR erasure that takes down production inference is operationally worse than delaying the erasure. The flag-and-require-explicit-migration contract preserves production while making the blocker visible.

**OPEN QUESTION**: GDPR exact semantics around derived data. If a subject's rows contributed to the training of a model that has since been re-trained on non-subject data, is the original model considered "containing personal data"? This spec's position: YES, because model weights can memorize training inputs. The original version must be deletable; only the new version that excludes the subject may be retained. Revisit once legal review is in.

### 7.3 Retention Defaults

**MUST**: The default retention policy, applied when no explicit policy is configured, MUST be:

- Runs under any alias: retain indefinitely
- Unaliased runs: retain 90 days
- Orphan artifacts (no reachable run or model): retain 30 days
- Erasure audit rows: retain indefinitely

**Why:** Production runs are operationally valuable forever; experimental runs become noise within a quarter. Defaults encode the obvious policy so teams don't ship with "retain forever."

---

## 8. Migration from MLflow

### 8.1 Import Entry Point

**MUST**: `km.import_mlflow(mlflow_uri, *, tenant_id, since=None, until=None, model_names=None)` MUST be the sole migration entry point. It MUST:

1. Connect to the MLflow tracking server at `mlflow_uri` (supports `http://`, `https://`, `file://`, `sqlite://`, `databricks://`)
2. Enumerate experiments within the optional time / name filters
3. Import each experiment, preserving `experiment_id`, `run_id`, metrics, params, tags, and artifacts
4. Re-verify every model artifact — if the artifact is pickle and an ONNX export is possible, emit a fresh ONNX artifact and flag the version `onnx_reexported=True`; if not possible, flag `onnx_status="legacy_pickle_only"`
5. Preserve MLflow stages as aliases — `"Production"` → alias `"production"`, etc.
6. Return a `MigrationReport` with counts (experiments, runs, models, artifacts, reexported, failed) and a per-record log of any import failures

**Why:** Bulk-importing preserves institutional history when teams migrate. Skipping ONNX re-verification means every migrated pickle-model silently falls through to the native prediction path and never gets the ONNX optimization. The re-export-or-flag contract makes that visible.

**OPEN QUESTION**: Scope of MLflow-import. Should we support streaming import of in-flight experiments (MLflow server still receiving writes while we copy)? Initial position: NO — recommend read-only MLflow snapshots for migration. Revisit if pressure from a specific migration customer surfaces.

### 8.2 Import Determinism

**MUST**: Re-running `km.import_mlflow()` against the same MLflow server MUST be idempotent — runs already imported (matched by `source_run_id` equal to MLflow's `run_id`) MUST NOT be duplicated. New runs since the last import MUST be imported. The `MigrationReport` MUST distinguish "imported-new" from "already-imported-skipped."

**Why:** A partial migration followed by a resume is the common real-world path. Non-idempotent import duplicates the last N runs on every resume.

---

## 9. In-Memory Mode

### 9.1 `sqlite+memory` Contract

**MUST**: `ExperimentTracker` and `ModelRegistry` MUST support `store="sqlite+memory"` (alias: `"sqlite:///:memory:"`). In this mode:

- No disk I/O — database lives in process memory
- `ArtifactStore` defaults to `SqliteBlobArtifactStore` within the same in-memory DB
- Process exit drops all runs, models, and artifacts — no persistence
- Intended for notebooks, unit tests, and interactive debugging

```python
# DO — notebook workflow with no persistence
async with km.track("sandbox", store="sqlite+memory") as t:
    await t.log_metric("acc", 0.85)
    # Everything disappears when the cell finishes
```

**Why:** Closes the user-reported pain point #8 in `00-synthesis-redesign-proposal.md §3.6` — the 1.x `ExperimentTracker` required a file-backed SQLite and could not use `:memory:`, blocking every notebook exploration workflow.

### 9.2 Explicit Mode Flag

**MUST**: `tracker.is_ephemeral: bool` MUST be True when the store is in-memory. Auto-capture MUST emit a WARN-level log on `__aenter__` stating "tracker is ephemeral — runs will not persist." The log MUST include the run_id so downstream log aggregators can correlate.

**Why:** Notebook users commonly forget they started in ephemeral mode and expect their results to be visible next session. The WARN is loud enough to catch the mistake on first use.

---

## 10. Cross-SDK Alignment

### 10.1 Shared Contract

This spec is **Python-Rust shared**. The API surface (method names, signatures modulo language conventions, storage key shape, tool names, error types) MUST match between kailash-py and kailash-rs. Per `rules/cross-sdk-inspection.md` (EATP D6), the SDKs carry independent implementations with matching semantics.

### 10.2 Rust Translation

| Clause                          | Python                                   | Rust                                                       |
| ------------------------------- | ---------------------------------------- | ---------------------------------------------------------- |
| Async context manager (§2.2)    | `async with km.track(...) as t:`         | `async_trait` + `tracker.with_run(|r| async { ... }).await` |
| ONNX export (default format §2.5) | `format="onnx"` via `skl2onnx` / `torch.onnx` | `tract-onnx` as the export backend                     |
| Storage backends (§4.1)         | `boto3`, `google-cloud-storage`, etc.    | `rust-s3`, `google-cloud-storage-rs`, `azure_storage`      |
| MCP surface (§5)                | `kailash-mcp` (Python)                   | `mcp-rs` (Rust)                                            |
| Polars return (§2.6)            | `polars.DataFrame`                       | `polars::DataFrame` (Rust polars)                          |
| Storage key shape (§6)          | Same `kailash_ml:v1:{tenant_id}:...`     | Same — binary-identical keys allow cross-SDK read         |

**MUST**: Rust reads of keys written by Python (and vice versa) MUST succeed without transformation. Cross-SDK interop tests (one written in Python, read in Rust; one written in Rust, read in Python) MUST live in `kailash-py/tests/cross_sdk/` and `kailash-rs/tests/cross_sdk/` respectively.

**Why:** The value proposition of cross-SDK alignment collapses the moment the wire formats drift. Mechanical key-shape equality is the cheapest guarantee against that drift.

### 10.3 Rust-Specific Notes

**MUST**: Rust `TrainingResult.accelerator` values MUST match the Python value set — `"cuda"`, `"mps"`, `"rocm"`, `"xpu"`, `"tpu"`, `"cpu"`. TPU support in Rust is marked N/A (`torch_xla` is Python-only) but the enum variant MUST exist so records imported from Python deserialize.

**Why:** Skipping the `TPU` variant in the Rust enum makes Python-written records unreadable in Rust and breaks the shared-contract claim.

---

## 11. Errors

### 11.1 Exception Hierarchy

**MUST**: All exceptions raised from `kailash_ml.tracker`, `kailash_ml.registry`, and `kailash_ml.artifacts` MUST inherit from `TrackingError`. Subclasses:

| Exception                      | Raised when                                                                      |
| ------------------------------ | -------------------------------------------------------------------------------- |
| `TrackerStoreInitError`        | Store URI cannot be initialized (permission, disk full, invalid connection)     |
| `TenantRequiredError`          | Multi-tenant mode without `tenant_id`                                            |
| `InvalidTenantIdError`         | `tenant_id` fails the safety regex                                               |
| `ModelSignatureRequiredError`  | `registry.register()` called without `signature`                                 |
| `LineageRequiredError`         | `registry.register()` called without a tracker context (no `tracker_run_id`)    |
| `ArtifactEncryptionError`      | Encrypt-then-store failed; includes `.reason` field                              |
| `ArtifactSizeExceededError`    | Artifact exceeds backend `max_artifact_bytes`                                    |
| `RunNotFoundError`             | `get_run(run_id)` with unknown run                                               |
| `ModelNotFoundError`           | `registry.get(name, version)` with unknown version                               |
| `AliasNotFoundError`           | `registry.get(name, alias=)` with unset alias                                    |
| `ErasureRefusedError`          | `delete_data_subject()` blocked by production alias                              |
| `MigrationImportError`         | MLflow import failed for a specific record (other records continue)              |

**Why:** Typed exceptions make error handling surgical. MLflow raises generic `Exception` in many paths, which forces downstream code to `except Exception: ...` and swallow unrelated errors.

---

## 12. Version

```python
from kailash_ml import __version__
assert __version__ == "2.0.0"
```

Both `packages/kailash-ml/pyproject.toml` and `packages/kailash-ml/src/kailash_ml/__init__.py` MUST report the same version (zero-tolerance Rule 5).

---

## Appendix A. MLflow Features Consciously NOT Matched

| MLflow feature         | Decision  | Reason                                                                                                 |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------------ |
| `mlflow.projects`      | NOT MATCHED | Replaced by Kaizen workflow orchestration per `rules/framework-first.md`. Reimplementing projects-as-entrypoints duplicates Kaizen. |
| `mlflow.evaluate`      | NOT MATCHED | Replaced by `engine.evaluate()` in `ml-engines.md`. Tracking records the run_id; evaluation is a training-spec concern. |
| Model flavors (`mlflow.sklearn`, `mlflow.pytorch`, ...) | NOT MATCHED | Replaced by `format=` parameter on `log_model`. Flavor-as-module proliferates import paths; `format="onnx"` defaults enforce one canonical format. |
| Model serving via MLflow REST | NOT MATCHED | Replaced by Nexus multi-channel serving (REST + MCP + CLI + WebSocket) per `nexus-channels.md`. |
| AutoLog for 13 frameworks | NOT MATCHED | Auto-capture is scoped to environment fields (§2.4). Per-framework autologging is brittle (MLflow auto-log for XGBoost has been broken across 4 MLflow versions). Users call `log_metric` explicitly. |
| System metrics (CPU, memory, GPU util) sampling | DEFERRED | Scope-deferred to a future `ml-observability.md`. Not worth coupling to tracking right now. |

## Appendix B. Open Questions

1. **GDPR semantics for derived models** (§7.2) — is a re-trained model considered to "contain" the original subject's data? Current position: YES. Awaiting legal review.
2. **MLflow import scope** (§8.1) — streaming vs snapshot only? Current position: snapshot only. Revisit on customer pressure.
3. **Alias vocabulary** (§3.3) — are the six reserved names (`production`, `staging`, `champion`, `challenger`, `canary`, `shadow`) the right set? Should `experiment` or `candidate` be reserved too?
4. **`diff_runs` reproducibility flag threshold** (§5.3) — is 5% metric delta the right trigger? Could be configurable per tenant.
5. **Artifact encryption key management** (§4.3) — this spec assumes the store uses backend-provided KMS integration. Should we specify a BYOK path? Defer to `security-data.md` when that spec is updated.
6. **Retention defaults** (§7.3) — 90 days for unaliased, 30 for orphan artifacts. Survey actual usage before locking.
7. **Cross-SDK TPU variant** (§10.3) — Python-only enum variants create Rust deserialization problems when the variant is absent. Accept lossy deserialize or require exhaustive variants? Current position: exhaustive.

---

_End of draft. Authored per `rules/specs-authority.md` and `rules/rule-authoring.md`. Promotes to `specs/ml-tracking.md` after human review. On promotion, supersedes the tracking sections of `specs/ml-engines.md` (§1.2 ModelRegistry, §1.6 ExperimentTracker) and registers in `specs/_index.md` alongside `ml-engines.md` and `ml-integration.md`._
