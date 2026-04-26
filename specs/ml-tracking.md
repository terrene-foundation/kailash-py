# Kailash ML Tracking — Canonical Experiment Tracker, Model Registry, Artifact Store

Version: 1.0.0 (draft)
Package: `kailash-ml`
Status: DRAFT at `workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md`. Promotes to `specs/ml-tracking.md` after round-2 /redteam convergence.
Supersedes: the round-1 draft at the same path; the tracking sections of `specs/ml-engines.md §1.2 (ModelRegistry)` and `§1.6 (ExperimentTracker)` when kailash-ml 1.0 ships.
Parent domain: ML Lifecycle.
Sibling specs: `ml-autolog.md`, `ml-diagnostics.md`, `ml-dashboard.md`, `ml-rl.md`, `ml-registry.md`, `ml-serving.md`, `ml-drift.md`, `ml-feature-store.md`, `ml-automl.md`, `ml-engines.md`.

Origin of this rewrite: `workspaces/kailash-ml-audit/04-validate/round-1-SYNTHESIS.md` theme T1 (two-tracker split, CRIT), T6 (spec-to-code drift, CRIT), T7 (industry parity, HIGH). Closes findings `round-1-spec-compliance.md:1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20`.

---

## 1. Scope + Non-Goals

### 1.1 In Scope

- **ONE** canonical experiment tracker engine (`ExperimentTracker`) that writes to **ONE** default database (`~/.kailash_ml/ml.db`) that **ONE** default dashboard (`MLDashboard`) reads from. The path `~/.kailash_ml/ml.db` is canonical across every spec in this bundle.
- Run lifecycle (start / finish / fail / kill), nested parent/child runs, SIGINT/SIGTERM auto-close.
- Logging primitives (`log_param`, `log_params`, `log_metric`, `log_metrics`, `log_artifact`, `log_figure`, `log_model`, `attach_training_result`, `set_tags`).
- Query primitives returning `polars.DataFrame` (NOT `list[Run]`).
- `diff_runs(run_a, run_b) -> RunDiff` with a frozen dataclass contract.
- Storage schema (SQLite default, Postgres production, `sqlite+memory` alias, S3 artifact backend).
- `kailash_ml:v1:{tenant_id}:{resource}:{id}` tenant-scoped keyspace per `rules/tenant-isolation.md` §1.
- `actor_id` kwarg + audit trail on every mutation.
- 15 typed exceptions in the `TrackingError` family (adds `MetricValueError` + `ParamValueError` to the round-1 list of 13, finite-check symmetry for both metric and param paths). Cross-cutting errors `UnsupportedTrainerError` (Decision 8) and `MultiTenantOpError` (Decision 12) sit at the `MLError` root alongside the family classes — see §9.1.
- `km.track()` contextvar that autolog, DL diagnostics, and RL diagnostics consume.
- `TrackerMCPServer` MCP surface for agent-driven introspection.
- `km.import_mlflow(uri, *, tenant_id=None)` bulk import from MLflow.
- `MLDashboard(db_url=None)` that defaults to the same canonical DB.
- Test matrix (Tier 1 unit per method + Tier 2 wiring `test_<method>_wiring.py` per `rules/facade-manager-detection.md` §2).

### 1.2 Out of Scope (Owned by Sibling Specs)

- Training itself → `ml-engines.md`.
- Auto-instrumentation of sklearn/Lightning/transformers/xgboost/lightgbm → `ml-autolog.md`.
- DL gradient/activation diagnostics → `ml-diagnostics.md`.
- Dashboard HTTP/SSE/WebSocket server implementation → `ml-dashboard.md`.
- RL reward-curve capture → `ml-rl.md`.
- Model serving → `ml-serving.md`.
- Drift → `ml-drift.md`.
- Feature store → `ml-feature-store.md`.
- AutoML orchestration → `ml-automl.md`.

### 1.3 Non-Goals

- **No second tracker.** The legacy `SQLiteTrackerBackend` class is DELETED at 1.0.0 (§2.3). The internal `SQLiteStorageDriver` is a private implementation detail of `ExperimentTracker`; the user-facing API is `ExperimentTracker` / `km.track()` only.
- **No MLflow-compat mode switch.** We import from MLflow; we do not serve the MLflow REST API.
- **No proprietary-vendor bridges** (`langfuse`, `langsmith`, `wandb`) in the tracking core — third-party sinks are a future extension, not 2.0 scope.

---

## 2. One-Tracker Contract

### 2.1 Canonical Engine

**MUST**: `ExperimentTracker` in `kailash_ml.engines.experiment_tracker` is the sole canonical tracker engine. `km.track()` is the async-context entry point that constructs an `ExperimentRun` wrapping the engine. A second user-facing tracker class is BLOCKED.

```python
# DO — single canonical path
import kailash_ml as km
async with km.track("my-exp") as run:
    await run.log_metric("loss", 0.32, step=1)

# DO NOT — parallel user-facing tracker (legacy class DELETED at 1.0.0)
from kailash_ml.tracking import SQLiteTrackerBackend  # BLOCKED — removed at 1.0.0
backend = SQLiteTrackerBackend("my.db")
backend.log_metric(...)
```

**Why:** Round-1 T1 documented `km.track()` → `ExperimentRun` writing to `~/.kailash_ml/ml.db` while `MLDashboard` read a second store path. The two DBs plus two code paths meant a `km.track()` run was invisible to the dashboard. A single canonical engine against a single canonical path (`~/.kailash_ml/ml.db`) is the only structural defense — `rules/facade-manager-detection.md` §1 applies.

**BLOCKED rationalizations:**

- "The 1.x engine stays for back-compat; the new one is parallel"
- "Two stores with a bridge class is cleaner than migrating"
- "Notebook users want a lighter API"

Origin: closes `round-1-spec-compliance.md:1.8, 1.9`; round-1 theme T1.

### 2.2 Default Store Path

**MUST**: The default database path is `~/.kailash_ml/ml.db` (resolved as `Path.home() / ".kailash_ml" / "ml.db"`). This path is used by BOTH `km.track()` AND `MLDashboard()` when neither caller passes an explicit `store=` / `db_url=`. Any other default is BLOCKED.

```python
# DO — single default
async with km.track("x") as run: ...                       # writes ~/.kailash_ml/ml.db
dashboard = MLDashboard()                                  # reads ~/.kailash_ml/ml.db
dashboard.start()

# DO NOT — separate default for dashboard
dashboard = MLDashboard(db_url="sqlite:///some-other.db")  # BLOCKED as default
```

**Why:** `packages/kailash-ml/src/kailash_ml/dashboard/__init__.py:46` in 0.x shipped a divergent default path, splitting every first-time user's data across two files. The canonical `~/.kailash_ml/ml.db` is the only path any ML primitive defaults to; `MLDashboard()`, `km.track()`, and every engine referenced in `ml-engines-v2-addendum §E1.1` read or write the same single location. The `1_0_0_merge_legacy_stores` numbered migration (§16) consolidates any 0.x alternate-path content into `ml.db` atomically on upgrade.

Origin: closes `round-1-spec-compliance.md:1.8`.

### 2.3 Storage-Driver Migration

**MUST**: The legacy `kailash_ml.tracking.sqlite_backend.SQLiteTrackerBackend` class is **DELETED** at 1.0.0 per Decision 14 (breaking-change list) and `rules/orphan-detection.md` §3 (removed = deleted, not deprecated). The internal storage surface is replaced by `kailash_ml._storage.sqlite_driver.SQLiteStorageDriver`, consumed ONLY by `ExperimentTracker`. No deprecation shim, no `DeprecationWarning` re-export, no compatibility alias. Users upgrading from 0.x MUST switch to `km.track()` / `ExperimentTracker.create()`.

```python
# DO — internal storage driver
# kailash_ml/engines/experiment_tracker.py
from kailash_ml._storage.sqlite_driver import SQLiteStorageDriver  # renamed + moved

# DO NOT — public class import path (DELETED at 1.0.0)
from kailash_ml.tracking import SQLiteTrackerBackend  # BLOCKED — class removed
```

**Why:** `rules/orphan-detection.md` §3: removed = deleted, not deprecated. A `DeprecationWarning` shim leaves the orphan pattern alive for another release cycle and continues to mislead users into the split-store bug. 1.0.0 is the MAJOR boundary per Decision 14; breaking removal is correct disposition. The `1_0_0_delete_sqlitetrackerbackend` numbered migration (§16) removes the import at the same atomic upgrade point where the legacy store is consolidated.

### 2.4 `ExperimentRun` Becomes A Thin Wrapper

**MUST**: The legacy `ExperimentRun` class at `kailash_ml.tracking.runner` MUST become a thin async-context-manager wrapper around the engine's run handle. Every `ExperimentRun` method MUST delegate to the engine (no duplicate state, no duplicate SQL, no duplicate run_id generation).

```python
# DO — delegate to engine
class ExperimentRun:
    def __init__(self, tracker: "ExperimentTracker", run_record: RunRecord):
        self._tracker = tracker
        self._run = run_record

    async def log_metric(self, key, value, *, step=None, timestamp=None):
        return await self._tracker.log_metric(
            self._run.run_id, key, value, step=step, timestamp=timestamp,
        )

# DO NOT — parallel implementation
class ExperimentRun:
    def __init__(self, path: Path):
        # Any second storage layer that is NOT the engine is BLOCKED. The legacy
        # SQLiteTrackerBackend class (0.x) is DELETED at 1.0.0 (see §2.3).
        self._storage = _LegacyDirectSQLite(path)  # duplicates engine, splits state
```

**Why:** The two implementations are how the two DBs were born. One class owning the API, one class proxying to it, is the only long-term stable shape.

### 2.5 Canonical Async Construction (CRIT-2)

**MUST**: `ExperimentTracker` has ONE canonical async construction path:

```python
# kailash_ml/engines/experiment_tracker.py
class ExperimentTracker:
    @classmethod
    async def create(
        cls,
        store_url: Optional[str] = None,
        *,
        default_tenant_id: Optional[str] = None,
    ) -> "ExperimentTracker":
        """Sole async construction path for ExperimentTracker.

        Args:
            store_url: SQLite / Postgres / MySQL URL. When None, defaults to
                `f"sqlite:///{Path.home() / '.kailash_ml' / 'ml.db'}"` per §2.2.
                Accepts `sqlite+memory` alias per §6.1.
            default_tenant_id: Engine-level default tenant resolved at step 4
                of §7.2. Set only for single-tenant dev / notebook use.

        Returns:
            Fully-initialized ExperimentTracker ready for use.
        """
        ...
```

Store-URL resolution routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b` (single shared helper; hand-rolled `os.environ.get(...)` is BLOCKED per `rules/security.md` § Multi-Site Kwarg Plumbing). The `store_url=None` default delegates the `KAILASH_ML_STORE_URL` / `KAILASH_ML_TRACKER_DB` bridge / `~/.kailash_ml/ml.db` precedence chain to the helper — sibling specs that construct an `ExperimentTracker` directly (`ml-rl-core §13.1`, `ml-rl-align-unification §4`, `ml-engines-v2 §2.3`, `ml-engines-v2-addendum §E1.2`) inherit the same precedence through the helper.

Every sibling spec that constructs an `ExperimentTracker` directly (e.g. `ml-rl-core §13.1`, `ml-rl-align-unification §4`, `ml-engines-v2 §2.3`, `ml-engines-v2-addendum §E1.2`) MUST call `await ExperimentTracker.create(...)`. Direct `ExperimentTracker(conn)` / `ExperimentTracker(...)` synchronous instantiation is BLOCKED as user-facing API.

```python
# DO — canonical async construction
tracker = await ExperimentTracker.create()                              # defaults to ~/.kailash_ml/ml.db
tracker = await ExperimentTracker.create(f"sqlite:///{tmp_path}/t.db")  # explicit path
tracker = await ExperimentTracker.create(store_url=None, default_tenant_id="dev")

# DO NOT — synchronous constructor as user API
tracker = ExperimentTracker(conn)          # BLOCKED — internal construction only
tracker = ExperimentTracker("path.db")     # BLOCKED — use .create(store_url=...)

# DO NOT — `.open()` or `.connect()` or other legacy factory names
tracker = await ExperimentTracker.open(default_tenant_id="dev")  # BLOCKED — rename to .create()
```

**Why:** A single canonical constructor is the entry-point for every wiring test and every sibling spec. Allowing both `ExperimentTracker(conn)` and `ExperimentTracker.create(...)` creates two init paths that drift (different schema setup, different connection lifecycle, different default-tenant resolution). CRIT-2 of the /redteam Phase-B closure pinned this as a hard rename — every reference in every spec is updated to `await ExperimentTracker.create(...)`.

Origin: CRIT-2 (round-2b closure verification); closes spec drift across ml-engines-v2, ml-rl-core, ml-rl-align-unification, ml-tracking.

---

## 3. Run Lifecycle

### 3.1 Entry-Point Signature

```python
@asynccontextmanager
async def track(
    experiment: str,
    *,
    tags: Optional[Mapping[str, str]] = None,
    tenant_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    store: Optional[Union[str, "ExperimentTracker"]] = None,
    data_subject_ids: Optional[List[str]] = None,
) -> AsyncIterator["ExperimentRun"]: ...
```

**MUST**: Every positional/keyword argument above MUST be honored. Silent ignore of `parent_run_id` (seen in round-1) or `tenant_id` (round-1 T3) is BLOCKED.

### 3.2 Status Transitions

**MUST**: A run's `status` field transitions strictly as:

```
RUNNING ─── normal exit ──▶ FINISHED
RUNNING ─── exception ──▶ FAILED  (exception re-raised, never swallowed)
RUNNING ─── SIGINT/SIGTERM/CancelledError ──▶ KILLED
```

`except: pass` on `__aexit__` is BLOCKED per `rules/zero-tolerance.md` Rule 3. The ONLY valid status values are `"RUNNING"`, `"FINISHED"`, `"FAILED"`, `"KILLED"` (Decision 3 — 4-member enum byte-identical with kailash-rs, see §3.5). `status="COMPLETED"` and `status="SUCCESS"` are NOT valid — any legacy 0.x rows carrying those values MUST be hard-coerced to `"FINISHED"` by the `1_0_0_rename_status` numbered migration (§16). No accept-on-read bridge; no runtime coercion fallback.

```python
# DO — re-raise, record FAILED
async def __aexit__(self, exc_type, exc, tb):
    if exc_type is asyncio.CancelledError:
        await self._tracker.finish_run(self._run.run_id, status="KILLED")
    elif exc_type is not None:
        await self._tracker.finish_run(
            self._run.run_id, status="FAILED", error=repr(exc),
        )
    else:
        await self._tracker.finish_run(self._run.run_id, status="FINISHED")
    return False  # never swallow

# DO NOT — silent swallow
async def __aexit__(self, exc_type, exc, tb):
    await self._tracker.finish_run(self._run.run_id, status="FINISHED")
    return True  # BLOCKED
```

### 3.3 SIGINT/SIGTERM Handling

**MUST**: On process-level SIGINT or SIGTERM received during an active run, the tracker MUST mark every currently-RUNNING run owned by this process as `KILLED` with `killed_reason="signal.SIGINT"` or `killed_reason="signal.SIGTERM"` before the process exits. Implementation MUST register a signal handler at `km.track()` entry that is idempotent across nested runs. Relying on Python's default SIGINT-to-KeyboardInterrupt translation alone is insufficient because a `kill -9` equivalent skips `__aexit__`.

### 3.4 Nested Runs

**MUST**: `parent_run_id=None` defaults to the ambient run resolved via `kailash_ml.tracking.get_current_run()` (§10.1). Passing `parent_run_id=parent.run_id` explicitly is equivalent. A run's `depth` column MUST be incremented from its parent's depth. Depth is unbounded.

```python
# DO — ambient parent, explicit parent both work
async with km.track("sweep") as parent:
    for trial in trials:
        async with km.track("trial") as child:              # ambient parent
            await child.log_metric("val_loss", trial.loss)

async with km.track("sweep") as parent:
    async with km.track("trial", parent_run_id=parent.run_id) as child:  # explicit
        ...
```

Origin: closes `round-1-SYNTHESIS.md` T6 nested-run ambiguity.

### 3.5 Cross-SDK Status Enum Parity (Decision 3)

**MUST**: The run-status enum MUST be the 4-member set `{RUNNING, FINISHED, FAILED, KILLED}` — byte-identical across kailash-py and kailash-rs. No variants, no aliases, no per-SDK extensions. Legacy values `COMPLETED` / `SUCCESS` / `SUCCEEDED` / `CANCELLED` / `DONE` are BLOCKED everywhere (write path, read path, MCP surface, dashboard DTO).

```python
# DO — the only valid status values
STATUS_RUNNING  = "RUNNING"
STATUS_FINISHED = "FINISHED"
STATUS_FAILED   = "FAILED"
STATUS_KILLED   = "KILLED"
_ALLOWED_STATUSES = frozenset({STATUS_RUNNING, STATUS_FINISHED, STATUS_FAILED, STATUS_KILLED})

# DO NOT — any other string
status = "COMPLETED"  # BLOCKED — legacy 0.x; migrate to FINISHED via 1_0_0_rename_status
status = "SUCCESS"    # BLOCKED — legacy 0.x; migrate to FINISHED via 1_0_0_rename_status
```

**Cross-SDK contract.** The kailash-rs `RunStatus` enum at `kailash-rs/crates/kailash-ml/src/tracking/status.rs` MUST declare the same four variants with the same serialized form. Cross-SDK follow-up tracked at kailash-rs#502 (open at the time of this spec). Any kailash-rs PR that deviates raises a cross-SDK review block per `rules/cross-sdk-inspection.md`.

**Why:** Polyglot deployments correlate run status across Python services and Rust services via the audit / event stream. A divergent enum value (e.g. Rust emits `SUCCEEDED` while Python writes `FINISHED`) breaks every `WHERE status = 'FINISHED'` query and every dashboard panel that groups by status. The 4-member lock is the same stable-fingerprint discipline used by `rules/event-payload-classification.md` §2 for record-id hashing.

Origin: Decision 3 (approved 2026-04-21). Kailash-rs cross-SDK todo: kailash-rs#502.

---

## 4. Logging Primitives

### 4.1 Parameters

```python
async def log_param(self, key: str, value: Any) -> None: ...
async def log_params(self, mapping: Mapping[str, Any]) -> None: ...
```

**MUST**: `value` is JSON-serialisable or coerced via `repr()` with a DEBUG log line. Keys follow `^[a-zA-Z_][a-zA-Z0-9_.\-]*$` — failing regex raises `ValueError`.

**MUST — Finite Check On Numeric Params**: When `isinstance(value, (int, float))`, `log_param` / `log_params` MUST validate `math.isfinite(value)`. `NaN` / `±Inf` param values are BLOCKED via `ParamValueError` — silent coercion to `None` / `0.0` / `str(value)` is BLOCKED.

```python
# DO — param finite-check mirrors metric finite-check
await run.log_param("learning_rate", float("nan"))  # raises ParamValueError

# DO NOT — silent coerce to string "nan"
```

**Why:** `log_param("learning_rate", float("nan"))` is currently not validated but downstream comparison queries (`WHERE params->>'learning_rate' = ?`) break on NaN because NaN != NaN. The finite-check aligns the param path with the metric path (§4.2) — one rule covers both.

### 4.2 Metrics (THE ROUND-1 CRIT GAP)

```python
async def log_metric(
    self,
    key: str,
    value: float,
    *,
    step: Optional[int] = None,
    timestamp: Optional[datetime] = None,
) -> None: ...

async def log_metrics(
    self,
    mapping: Mapping[str, float],
    *,
    step: Optional[int] = None,
    timestamp: Optional[datetime] = None,
) -> None: ...
```

**MUST**: `value` MUST be validated via `math.isfinite(value)`. `NaN`, `+inf`, `-inf` MUST raise `MetricValueError` (see §8). Silent coercion to `None`, `0.0`, or `str(value)` is BLOCKED.

```python
# DO — finite-check, typed error
import math
def _validate_metric_value(key: str, value: float) -> None:
    if not isinstance(value, (int, float)):
        raise MetricValueError(f"metric {key!r} must be numeric, got {type(value).__name__}")
    v = float(value)
    if not math.isfinite(v):
        raise MetricValueError(f"metric {key!r} value={v} is not finite")

# DO NOT — silent coerce
await run.log_metric("loss", float("nan"))  # BLOCKED: raises MetricValueError
```

**MUST**: `log_metric` MUST exist on the `ExperimentRun` object returned by `km.track()` (round-1 CRIT finding `1.3`). `log_metrics` MUST exist (round-1 `1.3`). `step` and `timestamp` keyword-only arguments MUST be honored (round-1 `1.4`).

**Why:** Round-1 `round-1-industry-competitive.md` H-2 documented this as "sub-parity with MLflow 1.0, 2018." Every MLflow/W&B/Lightning tutorial since 2018 assumes `log_metric`. Missing it is an 8-year-old muscle-memory failure.

Origin: closes `round-1-spec-compliance.md:1.3, 1.4`; closes industry H-2.

### 4.3 Artifacts

```python
async def log_artifact(
    self,
    path_or_bytes: Union[str, Path, bytes],
    name: str,
    *,
    content_type: Optional[str] = None,
    data_subject_ids: Optional[List[str]] = None,
) -> ArtifactHandle: ...
```

**MUST**: Content-addressed (SHA-256). Second call with identical bytes returns the same `ArtifactHandle`. Encryption failure raises `ArtifactEncryptionError` — silent plaintext fallback is BLOCKED. Size exceeding the backend's `max_artifact_bytes` raises `ArtifactSizeExceededError`.

### 4.4 Figures (DL Diagnostics Event Sink)

```python
async def log_figure(
    self,
    figure: Union["plotly.graph_objs.Figure", "matplotlib.figure.Figure"],
    name: str,
    *,
    step: Optional[int] = None,
) -> ArtifactHandle: ...
```

**MUST**: `log_figure` MUST serialize plotly figures via `figure.to_json()` and matplotlib figures via `fig.savefig(buf, format="png")`. The MIME type is recorded as `application/vnd.plotly.v1+json` or `image/png`. This is the sink `DLDiagnostics` and `RLDiagnostics` emit to.

**Why:** Round-1 T2: `DLDiagnostics` has an in-memory plotly figure but no path to the tracker. `log_figure` is the missing wire.

### 4.5 Model

```python
async def log_model(
    self,
    model: Any,
    name: str,
    *,
    format: str = "onnx",   # "onnx" | "pickle" | "torch" | "lightning" | "sklearn"
    aliases: Optional[List[str]] = None,
    signature: Optional[ModelSignature] = None,
    lineage: Optional[Mapping[str, Any]] = None,
    training_result: Optional["TrainingResult"] = None,
) -> "ModelVersionInfo": ...
```

**MUST**: `signature is None` raises `ModelSignatureRequiredError`. `lineage is None AND self._run is None` raises `LineageRequiredError`. When called inside a `km.track()` block, `tracker_run_id` is auto-populated from the ambient run; calling outside raises `LineageRequiredError`.

Origin: closes `round-1-spec-compliance.md:1.10, 1.11`.

### 4.6 Attach Training Result

```python
async def attach_training_result(self, result: "TrainingResult") -> None: ...
```

**MUST**: Persists `result.device: DeviceReport` into the run's envelope. For SQL/BI convenience, `attach_training_result` ALSO projects the DeviceReport into the three flattened `_kml_run` columns (`device_used`, `accelerator`, `precision`) using the same `device.backend_name` / `device.family` / `device.precision` mapping that `TrainingResult.__post_init__` uses for its 1.x back-compat mirrors (see `ml-engines-v2.md §4.1`). `result.seed_report` is persisted unchanged. These projections MUST use the canonical `DeviceReport` fields — storing a different string in the flat column than what `device.backend_name` would produce is BLOCKED (breaks the `TrainingResult.device` ⇔ `_kml_run.device_used` invariant).

#### MUST: Resume HP-Diff Emission

When the current run has a `parent_run_id` set (the run was created via `km.track(..., parent_run_id=<prior>)` as part of a `resume_from` checkpoint restore), `attach_training_result` MUST compute the HYPERPARAMETER DIFF against the parent run's final `hyperparameters` and:

1. Log each changed HP as two params: `params.{key}.old` = parent value, `params.{key}.new` = current value.
2. Emit a metric `resume.hp_diff_count` = number of changed keys.
3. DEBUG-log the full diff under `tracker.resume.hp_diff` structured event.

```python
# Example — cosine-schedule restart with lowered LR on resume
async with km.track("fraud-v2", parent_run_id="run_abc") as child:
    child.log_param("learning_rate", 1e-4)  # parent had 3e-4
    # child.params["learning_rate.old"] = 3e-4 (auto-populated)
    # child.params["learning_rate.new"] = 1e-4
    # child.metric["resume.hp_diff_count"] = 1
```

**Why:** The `RLTrainingConfig.resume_from` contract (see `ml-rl-core.md` §9) allows intentional HP changes on resume (lowered LR for cosine restart, stricter exploration, etc.). Without a structural HP-diff emission, the change is silent — a post-hoc audit cannot distinguish "run resumed with same HPs" (bit-reproduction) from "run resumed with different HPs" (intentional mutation). The diff is part of the reproducibility audit trail.

### 4.7 Tags

```python
async def set_tags(self, **tags: str) -> None: ...
```

**MUST**: `tags` MUST be searchable via `search_runs(filter="tags.env = 'prod'")`. Tag values are strings; non-string tag values are coerced via `str()` with a DEBUG log line.

---

## 5. Query Primitives

### 5.1 Polars Return (ROUND-1 SPEC VIOLATION)

```python
async def get_run(self, run_id: str, *, tenant_id: Optional[str] = None) -> RunRecord: ...
async def list_runs(
    self,
    *,
    experiment: Optional[str] = None,
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> pl.DataFrame: ...
async def search_runs(
    self,
    *,
    filter: Optional[str] = None,
    order_by: Optional[str] = None,
    limit: int = 100,
    tenant_id: Optional[str] = None,
) -> pl.DataFrame: ...
async def list_experiments(self, *, tenant_id: Optional[str] = None) -> pl.DataFrame: ...
async def list_metrics(self, run_id: str, *, tenant_id: Optional[str] = None) -> pl.DataFrame: ...
async def list_artifacts(self, run_id: str, *, tenant_id: Optional[str] = None) -> pl.DataFrame: ...
```

**MUST**: `list_runs`, `search_runs`, `list_experiments`, `list_metrics`, `list_artifacts` MUST return `polars.DataFrame`. `list[Run]` / `list[dict]` / `pandas.DataFrame` returns are BLOCKED.

Origin: closes `round-1-spec-compliance.md:1.5` (currently `search_runs` returns `list[Run]` at `engines/experiment_tracker.py:791`).

### 5.2 Filter Syntax

**MUST**: `filter` accepts the MLflow-compatible expression grammar:

```
<term> := "metrics." <name> <op> <value>
        | "params." <name> <op> <value>
        | "tags." <name> <op> <value>
        | "attributes." <name> <op> <value>
        | "env." <name> <op> <value>
<op> := "=" | "!=" | ">" | ">=" | "<" | "<=" | "LIKE" | "IN"
<filter> := <term> ( ("AND" | "OR") <term> )*
```

Parse errors raise `ValueError("invalid filter: …")` — silent accept-anything is BLOCKED.

### 5.3 `diff_runs` (ROUND-1 MISSING)

```python
@dataclass(frozen=True)
class ParamDelta:
    key: str
    value_a: Any
    value_b: Any
    changed: bool

@dataclass(frozen=True)
class MetricDelta:
    key: str
    value_a: Optional[float]
    value_b: Optional[float]
    delta: Optional[float]
    pct_change: Optional[float]
    per_step: Optional[pl.DataFrame]  # when both runs logged steps

@dataclass(frozen=True)
class EnvDelta:
    key: str
    value_a: Any
    value_b: Any
    changed: bool

@dataclass(frozen=True)
class RunDiff:
    run_id_a: str
    run_id_b: str
    params: Dict[str, ParamDelta]
    metrics: Dict[str, MetricDelta]
    environment: Dict[str, EnvDelta]
    reproducibility_risk: bool  # True when git_sha differs AND cuda_version differs AND max pct_change > 5%
    summary: str

async def diff_runs(
    self,
    run_a: str,
    run_b: str,
    *,
    tenant_id: Optional[str] = None,
) -> RunDiff: ...
```

**MUST**: `RunDiff` is a frozen dataclass. `reproducibility_risk` MUST be a typed boolean field, not a free-text note. Implementation MUST live at `kailash_ml.engines.experiment_tracker.diff_runs` — the module-level `diff_runs` function consumed by `km.diff_runs()` is a thin wrapper.

Origin: closes `round-1-spec-compliance.md:1.13` (grep currently empty).

---

## 6. Storage Layer

### 6.1 Backends

| URI scheme           | Driver class                       | Use case                                    |
| -------------------- | ---------------------------------- | ------------------------------------------- |
| `sqlite:///path.db`  | `SQLiteStorageDriver`              | Default (local single-file)                 |
| `sqlite:///:memory:` | `SQLiteStorageDriver` + `:memory:` | Unit tests; alias accepted: `sqlite+memory` |
| `sqlite+memory`      | Same as above (readability alias)  | Notebook workflows                          |
| `postgresql://...`   | `PostgresStorageDriver`            | Production multi-user                       |
| `mysql://...`        | `MySQLStorageDriver`               | Production multi-user                       |

**MUST**: `sqlite+memory` MUST be accepted (round-1 `1.6` HIGH — currently unsupported). Conversion is literal: `"sqlite+memory"` → `"sqlite:///:memory:"`.

Origin: closes `round-1-spec-compliance.md:1.6`.

### 6.2 Artifact Backends

`file://`, `sqlite://` (blob), `s3://`, `gs://`, `azure://`, `http(s)://` (read-only for MLflow migration). S3 is the default for prod; local SQLite blob is the default for notebooks.

### 6.3 Schema DDL

All DDL lives in numbered migrations under `packages/kailash-ml/src/kailash_ml/_storage/migrations/` per `rules/schema-migration.md` §1. Below is the canonical table shape (PostgreSQL dialect shown — SQLite uses `TEXT`/`INTEGER` equivalents):

```sql
CREATE TABLE _kml_experiment (
    tenant_id       TEXT        NOT NULL,
    experiment_id   TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    owner_actor_id  TEXT,
    PRIMARY KEY (tenant_id, experiment_id),
    UNIQUE (tenant_id, name)
);

CREATE TABLE _kml_run (
    tenant_id       TEXT        NOT NULL,
    run_id          TEXT        NOT NULL,
    experiment_id   TEXT        NOT NULL,
    parent_run_id   TEXT,
    depth           INTEGER     NOT NULL DEFAULT 0,
    status          TEXT        NOT NULL,   -- RUNNING|FINISHED|FAILED|KILLED
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ,
    host            TEXT,
    git_sha         TEXT,
    git_dirty       BOOLEAN,
    python_version  TEXT,
    kailash_ml_version TEXT,
    lightning_version TEXT,
    torch_version   TEXT,
    cuda_version    TEXT,
    -- Flattened projections of TrainingResult.device: DeviceReport.
    -- _kml_run mirrors the 1.x back-compat fields (device_used/accelerator/precision)
    -- for BI/SQL query convenience; the authoritative source-of-truth remains the
    -- serialized DeviceReport persisted in the per-run envelope artifact.
    device_used     TEXT,   -- == TrainingResult.device.backend_name
    accelerator     TEXT,   -- == TrainingResult.device.family
    precision       TEXT,   -- == TrainingResult.device.precision
    actor_id        TEXT,
    killed_reason   TEXT,
    error           TEXT,
    data_subject_ids TEXT[],
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id, experiment_id) REFERENCES _kml_experiment(tenant_id, experiment_id)
);
CREATE INDEX _kml_run_parent ON _kml_run(tenant_id, parent_run_id);
CREATE INDEX _kml_run_actor_time ON _kml_run(tenant_id, actor_id, start_time);

CREATE TABLE _kml_param (
    tenant_id TEXT NOT NULL,
    run_id    TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     JSONB NOT NULL,
    PRIMARY KEY (tenant_id, run_id, key)
);

CREATE TABLE _kml_metric (
    tenant_id TEXT        NOT NULL,
    run_id    TEXT        NOT NULL,
    key       TEXT        NOT NULL,
    value     DOUBLE PRECISION NOT NULL,
    step      BIGINT,            -- int64 — covers batch-level step counters on 100B-token training runs
    timestamp TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, run_id, key, step)
);
-- MUST: step is BIGINT (int64), NOT INTEGER (int32). A tokens/sec of 100K on a
-- 100B-parameter model hits 2^32 in 11 hours; 2^63 never. SQLite INTEGER is
-- already int64 so the SQLite migration is a no-op; PostgreSQL INTEGER is 32-bit
-- so a regression test (see §14.4) MUST insert step = 2_500_000_000 and read it
-- back unchanged.

CREATE TABLE _kml_tag (
    tenant_id TEXT NOT NULL,
    run_id    TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id, key)
);

CREATE TABLE _kml_artifact (
    tenant_id       TEXT        NOT NULL,
    artifact_id     TEXT        NOT NULL,
    run_id          TEXT        NOT NULL,
    sha256          TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    content_type    TEXT,
    size_bytes      BIGINT      NOT NULL,
    storage_uri     TEXT        NOT NULL,
    encrypted       BOOLEAN     NOT NULL DEFAULT FALSE,
    data_subject_ids TEXT[],
    created_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, artifact_id)
);
CREATE INDEX _kml_artifact_sha ON _kml_artifact(tenant_id, sha256);

CREATE TABLE _kml_audit (
    audit_id      BIGSERIAL   PRIMARY KEY,
    tenant_id     TEXT        NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    actor_id      TEXT        NOT NULL,
    resource_kind TEXT        NOT NULL,  -- run|model|artifact|alias|experiment
    resource_id   TEXT        NOT NULL,
    action        TEXT        NOT NULL,  -- create|update|delete|promote|erase
    prev_state    JSONB,
    new_state     JSONB
);
CREATE INDEX _kml_audit_lookup ON _kml_audit(tenant_id, actor_id, timestamp);

CREATE TABLE _kml_lineage (
    tenant_id     TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    version       INTEGER NOT NULL,
    tracker_run_id TEXT NOT NULL,
    parent_version INTEGER,
    training_data_uri TEXT,
    feature_store_version TEXT,
    base_model_uri TEXT,
    PRIMARY KEY (tenant_id, model_name, version)
);
```

**MUST**: Migrations are numbered (`0001_create_kml_experiment.py`, ...) and reversible (`rules/schema-migration.md` §3). Destructive migrations require `force_downgrade=True` per `rules/schema-migration.md` §7. Migration filenames use the bare `kml_experiment` stem (Python identifier rules — leading underscore on a module name is reserved); the physical table name is `_kml_experiment` as declared in §6.3 DDL.

#### Cross-Engine `LineageGraph` — DEFERRED to Wave 6.5b (W6-014, issue #657)

The cross-engine lineage SURFACE (`km.lineage(...)` returning a frozen `LineageGraph` per `ml-engines-v2-addendum §E10.2`, plus the registry-side `ModelRegistry.build_lineage_graph()` walker that traverses the `_kml_lineage` table above) is DEFERRED to Wave 6.5b. The DDL above ships with the 1.0.0 release; the traversal walker + Python-surface frozen dataclass do not.

**Status — 1.0.0:**

- `_kml_lineage` table ships per the DDL above; mutations populate `tracker_run_id`, `parent_version`, `training_data_uri`, `feature_store_version`, `base_model_uri` as designed.
- `km.lineage(ref, *, tenant_id=None, max_depth=10)` raises `LineageNotImplementedError` (a `TrackingError` subclass — see §9.1).
- `kailash_ml.LineageGraph` is REMOVED from the public surface (no placeholder type; `rules/zero-tolerance.md` Rule 2 — fake data BLOCKED).

**Disposition rationale per `rules/zero-tolerance.md` Rule 1b (4 conditions met):**

1. Runtime-safety proof — typed `LineageNotImplementedError` raised; no fake graph returned.
2. Tracking issue — terrene-foundation/kailash-py#657.
3. Release PR body link — W6-014 PR references #657 in body.
4. Release-specialist signoff — covered by Wave 6 plan § "Deferral discipline".

**Wave 6.5b implementation contract:**

- Land `kailash_ml/engines/lineage.py` with frozen `LineageGraph` / `LineageNode` / `LineageEdge` dataclasses per `ml-engines-v2-addendum §E10.2`.
- Implement `ModelRegistry.build_lineage_graph(*, ref, tenant_id, max_depth) -> LineageGraph` traversing `_kml_lineage` via DataFlow primitives (NOT raw SQL — `rules/framework-first.md`).
- Cross-tenant traversal raises `CrossTenantLineageError` per `rules/tenant-isolation.md`.
- `km.lineage(...)` switches from raising `LineageNotImplementedError` to returning the real graph; the typed error class is removed from `errors.py` `__all__` in the same PR (`rules/orphan-detection.md` Rule 4 — API removal sweeps tests).
- Tier 2 wiring test `tests/integration/test_lineage_graph_wiring.py` per `rules/facade-manager-detection.md` MUST Rule 2.
- End-to-end regression `tests/regression/test_readme_lineage_quickstart.py` per `rules/testing.md` § "End-to-End Pipeline Regression".

---

## 7. Tenant-Isolation Keyspace

### 7.1 Key Shape

**MUST**: Every cache-level and lookup-level key MUST follow `kailash_ml:v1:{tenant_id}:{resource}:{id}`:

| Resource   | Key shape                                            |
| ---------- | ---------------------------------------------------- |
| Experiment | `kailash_ml:v1:{tenant_id}:exp:{experiment_id}`      |
| Run        | `kailash_ml:v1:{tenant_id}:run:{run_id}`             |
| Model      | `kailash_ml:v1:{tenant_id}:model:{name}:{version}`   |
| Alias      | `kailash_ml:v1:{tenant_id}:alias:{name}:{alias}`     |
| Artifact   | `kailash_ml:v1:{tenant_id}:artifact:{sha256}`        |
| Lineage    | `kailash_ml:v1:{tenant_id}:lineage:{name}:{version}` |

Round-1 grep confirmed `kailash_ml:v1:` appears zero times in source. This closes that gap.

Origin: closes `round-1-spec-compliance.md:1.14`; `rules/tenant-isolation.md` §1.

### 7.2 Tenant-ID Resolution Order

**MUST**: `tenant_id` is set at session boundary (`km.track(tenant_id=...)` or engine construction) and flows through the ambient contextvar per §10.2. Per-mutation `tenant_id=` kwargs are BLOCKED on user-facing primitives (HIGH-4 round-1 finding). The MCP surface (§11) is the exception and accepts explicit `tenant_id` because no contextvar crosses the MCP boundary.

Resolution order (applied at session boundary, read at mutation time via `get_current_tenant_id()`):

1. `km.track(tenant_id="acme")` kwarg at session entry.
2. Ambient `get_current_tenant_id()` when constructing a nested `km.track()`.
3. `KAILASH_TENANT_ID` environment variable.
4. Engine-construction default set via `await ExperimentTracker.create(store_url=None, default_tenant_id="dev")` (§2.5).
5. If none of the above AND `multi_tenant=True` was set on the engine → raise `TenantRequiredError`.
6. If `multi_tenant=False` (default for dev), the tenant dimension is set to the literal string `"_single"` — NOT `"default"`, NOT `""`, and NOT `"global"`.

#### MUST: `"_single"` Is The Canonical Cross-Spec Single-Tenant Sentinel

The literal `"_single"` is the canonical single-tenant `tenant_id` sentinel across every kailash-ml engine (`ExperimentTracker`, `ModelRegistry`, `FeatureStore`, `InferenceServer`, `MLDashboard`). Every spec that materialises a `tenant_id` for a single-tenant deployment MUST use this exact string. The alternative sentinel `"global"` seen in earlier drafts is BLOCKED — `ml-tracking.md` is the authority per Decision 10 (single-spec-per-domain).

```python
# DO — canonical sentinel across every engine
tenant_id = "_single"   # FeatureStore, ModelRegistry, Tracker, Serving, Dashboard

# DO NOT — drift from the canonical form
tenant_id = "global"    # BLOCKED — ml-tracking.md §7.2 authority
tenant_id = "default"   # BLOCKED — rules/tenant-isolation.md §2
tenant_id = ""          # BLOCKED — silent empty
```

**Why:** A cross-engine query "show me every run that ran against version 7 of `fraud`" must JOIN across the tracker table and the registry table on `tenant_id`. If the tracker stores `"_single"` while the registry stores `"global"`, every single-tenant user's join returns zero rows. The canonical-sentinel rule closes this by pinning every engine to the same literal. Leading underscore guarantees the sentinel is never confused with a real tenant identifier (identifiers per `rules/dataflow-identifier-safety.md` §2 match `^[a-zA-Z_][a-zA-Z0-9_]*$` — `_single` starts with underscore, marking it as a system-reserved identifier).

```python
# DO — session-level tenant in multi-tenant mode; metrics flow through ambient
async with km.track("exp", tenant_id="acme") as run:
    await run.log_metric("loss", 0.32, step=1)   # tenant resolved from ambient

# DO NOT — per-call tenant kwarg on user-facing primitives (HIGH-4 round-1 finding)
await run.log_metric("loss", 0.32, tenant_id="acme")   # BLOCKED

# DO NOT — silent fallback to "default" in multi-tenant mode
# BLOCKED per rules/tenant-isolation.md §2
```

Origin: closes `round-1-spec-compliance.md:1.15`; `rules/tenant-isolation.md` §2; HIGH-4 round-1 finding pinning.

### 7.3 Invalidation

**MUST**: `tracker.invalidate_experiment(name, *, tenant_id)` and `registry.invalidate_model(name, *, tenant_id)` MUST accept `tenant_id`. Omitting it requires explicit `tenant_id=None` AND the caller's admin authority (checked via PACT envelope).

---

## 8. Actor / Audit / GDPR Contract

### 8.1 Actor Resolution (HIGH-4)

**MUST**: Every user-facing mutation primitive (`log_param`, `log_metric`, `log_artifact`, `log_model`, `set_alias`, `delete_alias`, `delete_data_subject`, `set_tags`, `log_figure`, `attach_training_result`) resolves `actor_id` from the ambient contextvar. The user-facing signature does NOT take `actor_id=` as a per-call kwarg — actor identity is a session-level property, not a per-metric property, per HIGH-4 round-1 finding. The MCP surface (§11) is the ONLY exception: cross-process tool calls receive `(run_id, tenant_id, actor_id)` explicitly because no contextvar exists across the MCP boundary.

```python
# DO — actor flows from the session (km.track entry) through contextvar
async with km.track("my-exp", actor_id="alice@acme.com") as run:
    await run.log_metric("loss", 0.32, step=1)        # actor resolved from ambient
    await run.log_param("lr", 1e-3)                    # same actor, no kwarg plumbing

# DO NOT — actor as per-call kwarg
await run.log_metric("loss", 0.32, actor_id="alice")   # BLOCKED — violates HIGH-4 round-1 finding
await run.log_param("lr", 1e-3, actor_id="alice")      # BLOCKED — same
```

**Resolution order** (for both `tenant_id` and `actor_id`):

1. Ambient `get_current_run()` already carries the values established at `km.track(...)` entry.
2. `km.track(actor_id=..., tenant_id=...)` entry kwargs.
3. `KAILASH_ACTOR_ID` / `KAILASH_TENANT_ID` env vars.
4. Engine-construction defaults (`ExperimentTracker.create(default_tenant_id="dev")`).
5. If `multi_tenant=True` and no tenant_id resolved → raise `TenantRequiredError`.
6. If `require_actor=True` and no actor_id resolved → raise `ActorRequiredError`.
7. If `multi_tenant=False` and no tenant_id → `"_single"` sentinel (NOT `"default"`).

`require_actor` defaults to `False` in single-tenant dev mode, flips to `True` when `multi_tenant=True` is set at engine construction. Per HIGH-4 round-1 finding (TBD triage T-04).

### 8.2 Audit Row Persistence

**MUST**: Every mutation MUST write ONE row to `_kml_audit` with fields `(timestamp, actor_id, tenant_id, resource_kind, resource_id, action, prev_state, new_state)`. The row is written in the SAME transaction as the mutation — split-transaction writes where the audit row can be lost are BLOCKED.

```python
# DO — same transaction
async with self._storage.transaction(tenant_id) as txn:
    await txn.execute("INSERT INTO _kml_metric ...", ...)
    await txn.execute("INSERT INTO _kml_audit ...", ...)

# DO NOT — audit outside transaction
await self._storage.insert_metric(...)
await self._storage.insert_audit(...)  # BLOCKED: metric without audit if crash mid-way
```

### 8.3 Audit Indexing

**MUST**: Index `_kml_audit` on `(tenant_id, actor_id, timestamp)` (schema §6.3 already declares this). "Show me everything actor `alice@acme.com` did to tenant `acme` this month" is a single indexed range scan.

### 8.4 GDPR Erasure — Audit Rows Are Immutable (Decision 2)

**MUST**: `delete_data_subject(data_subject_id, *, tenant_id)` DELETES run content, artifact content, and model content for every row whose `data_subject_ids TEXT[]` column contains `data_subject_id`. The erase job targets the following tables ONLY:

- `_kml_param` — delete rows for affected `run_id`.
- `_kml_metric` — delete rows for affected `run_id`.
- `_kml_artifact` — delete rows AND storage-backend object content (S3 `DELETE`, local file unlink).
- `_kml_model_artifact` — delete rows AND content-addressable storage objects per `ml-registry.md §7` (CAS GC).
- `_kml_run.data_subject_ids` — remove the `data_subject_id` entry from the array; if the array becomes empty, leave the run shell row but null-out `error`, `git_sha`, `host`, `killed_reason`.

**Audit rows are IMMUTABLE and MUST NOT be deleted or redacted.** The audit record of the erasure itself, AND every prior audit row referencing the erased content, persist with:

- `resource_id` hashed to `sha256:<8hex>` (first 8 hex chars of SHA-256) per `rules/event-payload-classification.md` §2.
- `prev_state` / `new_state` JSONB columns with any embedded classified PK values re-serialized through the same `sha256:<8hex>` fingerprint.
- The `actor_id` of the erasure call is recorded in a new audit row with `action='erase'` and `new_state={"data_subject_fingerprint": "sha256:<8hex>", "rows_deleted": <count>}`.

```sql
-- DO — hashed fingerprint, audit row persists
UPDATE _kml_audit
SET prev_state = jsonb_set(prev_state, '{record_id}', to_jsonb('sha256:' || substring(encode(sha256(prev_state->>'record_id'::text::bytea), 'hex'), 1, 8)))
WHERE prev_state ? 'record_id' AND prev_state->>'tenant_id' = $1 AND prev_state @> $2;
-- (no DELETE on _kml_audit)

-- DO NOT — delete the audit row
DELETE FROM _kml_audit WHERE resource_id = ANY(:erased_ids);  -- BLOCKED: destroys forensic chain
```

**Why:** GDPR explicitly recognizes audit/forensic records as lawful basis for retention (Article 17(3)(e)). Deleting the audit row defeats incident response and regulatory reporting. Hashed fingerprints give forensic correlation ("the same subject was the source of both events") without exposing the raw PII. Cross-SDK parity: identical fingerprint format to kailash-rs per `rules/event-payload-classification.md` §2.

**BLOCKED rationalizations:**

- "GDPR requires full erasure including audit"
- "The audit can be anonymized instead of hashed"
- "Leaving any trace of the subject contradicts the erasure request"
- "Hashed fingerprints are reversible so they count as PII"

**Response:** Regulator expectation is "the PII is unrecoverable from the stored record." `sha256:<8hex>` with 32 bits of entropy is not reversible against realistic PK spaces (UUIDs, emails, integers); is insufficient for rainbow-table attacks against the original value; and is sufficient for post-incident correlation. Audit rows containing these fingerprints are the institutional memory the erasure itself is audited against.

`ErasureRefusedError` is raised when the affected run is referenced by a production model alias (§9.1). The operator MUST first clear the production alias (`registry.delete_alias("production", actor_id=...)`) before re-running `delete_data_subject`.

Origin: Decision 2 (approved 2026-04-21). Cross-references: `rules/event-payload-classification.md` §2, `rules/tenant-isolation.md` §5 ("audit rows persist tenant_id").

---

## 9. Exception Taxonomy (CRIT-3 — Canonical Hierarchy)

### 9.1 `MLError` Root + Per-Domain Family (authoritative)

**MUST**: Every typed exception raised by `kailash-ml` MUST inherit from `kailash_ml.errors.MLError` (the package-level root) via the appropriate per-domain family error. No exception is "free-floating" — the declaration tree below is authoritative and MUST be mirrored in `packages/kailash-ml/src/kailash_ml/errors.py`. Every other spec in this bundle re-exports the family errors it raises via `from kailash_ml.errors import ...`.

```python
# kailash_ml/errors.py  — canonical hierarchy (authoritative)
class MLError(Exception):
    """Root of every typed exception raised by kailash-ml."""

# --- domain families (one per spec) ---
class TrackingError(MLError): ...
class AutologError(MLError): ...
class RLError(MLError): ...
class BackendError(MLError, RuntimeError): ...   # keeps `except RuntimeError` back-compat
class DriftMonitorError(MLError): ...
class InferenceServerError(MLError): ...
class ModelRegistryError(MLError): ...
class FeatureStoreError(MLError): ...
class AutoMLError(MLError): ...
class DiagnosticsError(MLError): ...
class DashboardError(MLError): ...

# --- cross-cutting errors (span multiple domains) ---
class UnsupportedTrainerError(MLError): ...          # Decision 8 — raised at Engine dispatch
class MultiTenantOpError(MLError): ...               # Decision 12 — cross-tenant admin ops

# --- tracking sub-types (TrackingError family) ---
class TrackerStoreInitError(TrackingError): ...
class InvalidTenantIdError(TrackingError): ...
class TenantRequiredError(TrackingError): ...
class ActorRequiredError(TrackingError): ...         # HIGH-4 round-1 finding (§8.1)
class ModelSignatureRequiredError(TrackingError): ...
class LineageRequiredError(TrackingError): ...
class LineageNotImplementedError(TrackingError): ...   # W6-014 deferral — see §6.3 + issue #657
class ArtifactEncryptionError(TrackingError): ...
class ArtifactSizeExceededError(TrackingError): ...
class AliasNotFoundError(TrackingError): ...
class ErasureRefusedError(TrackingError): ...
class MigrationImportError(TrackingError): ...
class RunNotFoundError(TrackingError): ...
class ExperimentNotFoundError(TrackingError): ...
class MetricValueError(TrackingError, ValueError): ...   # Phase-B Round 2b §A.1 T-03 SAFE-DEFAULT — keeps `except ValueError`
class ParamValueError(TrackingError, ValueError): ...    # NaN/Inf param finite-check, mirrors MetricValueError
```

**Family assignment rule**: an exception raised by a primitive in domain `D` inherits from `DError`. An exception raised by a cross-cutting primitive inherits from whichever domain owns the primary concern:

- `TenantRequiredError` is raised across every domain but lives under `TrackingError` (tenant resolution is a tracker concern at root) — other specs `from kailash_ml.errors import TenantRequiredError` and re-raise.
- `ActorRequiredError` — same pattern, TrackingError family.
- `BackendError` multi-inherits `RuntimeError` because 0.x code callers catch `except RuntimeError` and MUST continue to work at 1.0.0 (kwargs-plumbing parity from `rules/security.md` § Multi-Site Kwarg Plumbing).
- `MetricValueError` multi-inherits `ValueError` per Phase-B Round 2b §A.1 T-03 SAFE-DEFAULT so `except ValueError` continues to catch NaN/Inf rejections.
- `ParamValueError` multi-inherits `ValueError` per the same Phase-B T-03 pattern — keeps `except ValueError` catching NaN/Inf rejections on the param path (`log_param` / `log_params`, §4.1).
- `UnsupportedTrainerError` (Decision 8) is truly cross-cutting — raised at `MLEngine.fit()` dispatch time when a `Trainable.fit()` bypasses `L.Trainer`. It does NOT belong to a single domain family; it inherits directly from `MLError`. Every engine-integrating spec imports it from `kailash_ml.errors`. Declared originally in `ml-engines-v2-draft.md §3.2 MUST 2`; re-exported here in the canonical hierarchy.
- `MultiTenantOpError` (Decision 12) is truly cross-cutting — raised by any primitive that performs a cross-tenant admin operation without PACT D/T/R clearance (registry export/import, feature-store snapshot, serving shadow across tenants). It lives directly under `MLError` (not under `ModelRegistryError` alone) so every spec that gates on cross-tenant paths re-exports it. Canonical home per `supporting-specs-draft/kailash-core-ml-integration-draft.md §3.3` is `kailash.ml.errors.MultiTenantOpError`; kailash-ml re-exports it as `kailash_ml.errors.MultiTenantOpError` so callers in either import path work.

**MUST NOT**: A spec file MAY add sub-types under its family (e.g. `ReferenceNotFoundError(DriftMonitorError)` lives in `ml-drift.md`), but MUST NOT declare a new top-level family outside `kailash_ml.errors`. Every family declaration lives in one file.

### 9.1.1 Canonical Hierarchy Diagram

The hierarchy above is ALSO expressed as the following tree for visual reference. In case of any disagreement between the Python declaration block (§9.1) and this tree, the Python declaration is authoritative. Annotations `— NEW` mark entries introduced by round-3 spec-fix shard D (D1/D3/D4); decision annotations (`— Decision N`) reference `approved-decisions.md`.

```
MLError  (kailash_ml.errors)
├── TrackingError
│   ├── MetricValueError (TrackingError, ValueError)  — Phase-B Round 2b §A.1 T-03 pattern
│   ├── ParamValueError (TrackingError, ValueError)   — NEW (D4 shard)
│   ├── ActorRequiredError
│   ├── TenantRequiredError
│   ├── RunNotFoundError
│   ├── ExperimentNotFoundError
│   ├── TrackerStoreInitError
│   ├── InvalidTenantIdError
│   ├── ModelSignatureRequiredError
│   ├── LineageRequiredError
│   ├── LineageNotImplementedError              — W6-014 deferral (§6.3 + issue #657)
│   ├── ArtifactEncryptionError
│   ├── ArtifactSizeExceededError
│   ├── AliasNotFoundError
│   ├── ErasureRefusedError
│   └── MigrationImportError
├── AutologError
│   ├── AutologNoAmbientRunError
│   └── AutologUnknownFrameworkError
├── RLError
│   ├── RLEnvIncompatibleError
│   ├── RLPolicyShapeMismatchError
│   ├── ReplayBufferUnderflowError
│   ├── RewardModelRequiredError
│   └── FeatureNotYetSupportedError
├── BackendError (MLError, RuntimeError)
│   ├── UnsupportedPrecision
│   └── UnsupportedFamily
├── DriftMonitorError
│   ├── ReferenceNotFoundError
│   ├── InsufficientSamplesError
│   └── DriftThresholdError
├── InferenceServerError
│   ├── ModelLoadError
│   ├── InvalidInputSchemaError
│   ├── RateLimitExceededError
│   ├── TenantQuotaExceededError
│   ├── ShadowDivergenceError
│   └── OnnxExportUnsupportedOpsError      — NEW (D1 shard)
├── ModelRegistryError
│   ├── ModelNotFoundError
│   ├── AliasOccupiedError
│   ├── AliasNotFoundError                  (re-export; canonical home TrackingError)
│   ├── CrossTenantLineageError
│   ├── ImmutableGoldenReferenceError      — NEW (D3 shard)
│   └── TenantQuotaExceededError
├── FeatureStoreError
│   ├── FeatureNotFoundError
│   ├── StaleFeatureError
│   ├── PointInTimeViolationError
│   └── TenantQuotaExceededError
├── AutoMLError
│   ├── BudgetExhaustedError
│   ├── InsufficientTrialsError
│   └── EnsembleFailureError
├── DiagnosticsError
│   ├── DLDiagnosticsStateError
│   └── SeedReportError
├── DashboardError
│   ├── UnknownTenantError
│   ├── AuthorizationError
│   ├── LiveStreamError
│   ├── RateLimitExceededError
│   └── RunNotFoundInDashboardError
├── UnsupportedTrainerError                 — Decision 8 (cross-cutting, ml-engines-v2 §3.2 MUST 2)
└── MultiTenantOpError                      — Decision 12 (cross-cutting, kailash-core-ml-integration §3.3)
```

**Note on re-exports vs multi-inheritance**: the diagram shows `AliasNotFoundError` under BOTH `TrackingError` (canonical home — alias resolution is tracker-adjacent) and `ModelRegistryError` (so registry callers can catch it from the registry family). The Python-level declaration (`class AliasNotFoundError(TrackingError)`) is authoritative; the second appearance denotes a re-export for `except ModelRegistryError` ergonomics, not a second base class. Same pattern: `TenantQuotaExceededError` is declared once under whichever domain owns the primary quota check (registry, feature-store, or serving depending on call site); siblings re-export. No class multi-inherits from two domain families — that would ambiguate `except` order.

### 9.2 Package-Level Re-Export

**MUST**: `kailash_ml/__init__.py` MUST re-export every family error AND every tracking sub-type at the package root so `from kailash_ml import TenantRequiredError` works. Sibling specs (`ml-registry.md`, `ml-drift.md`, `ml-serving.md`, `ml-rl.md`, `ml-feature-store.md`, `ml-automl.md`, `ml-diagnostics.md`, `ml-dashboard.md`, `ml-autolog.md`, `ml-backends.md`) re-export their own family errors at sibling-package roots as well (e.g. `from kailash_ml.rl.errors import RLError`).

### 9.3 Raising Contract

**MUST**:

- A TrackingError sub-type (§9.1) MUST be used for every typed raise path in this spec.
- A plain `Exception`, `RuntimeError`, or `ValueError` from any code path under `kailash_ml.tracking` / `kailash_ml.engines.experiment_tracker` is BLOCKED — the typed hierarchy is the public contract.
- Exception messages MUST NOT echo a raw user-supplied `tenant_id`, `run_id`, or `filter` verbatim — they embed a short hash fingerprint instead (same pattern as `rules/dataflow-identifier-safety.md` §2). Prevents stored-XSS-via-log-poisoning.

Origin: closes `round-1-spec-compliance.md:1.19`; CRIT-3 (error hierarchy); Phase-B Round 2b §A.1 T-03 SAFE-DEFAULT (MetricValueError multi-inherit).

---

## 10. Contextvar Propagation (CRIT-4 — Public Accessor)

### 10.1 Public Accessor — `get_current_run()`

**MUST**: The public API for reading the ambient run is the module-level function `kailash_ml.tracking.get_current_run() -> Optional[ExperimentRun]`. Every sibling spec in this bundle (`ml-autolog`, `ml-diagnostics`, `ml-rl-core`, `ml-serving`, `ml-automl`, `ml-drift`, `ml-engines-v2`, `ml-engines-v2-addendum`, `ml-registry`, `ml-feature-store`, `ml-dashboard`) reads the ambient run through this accessor. Direct access to the internal `ContextVar` object is BLOCKED for library callers.

```python
# DO — public accessor
from kailash_ml.tracking import get_current_run

run = get_current_run()           # Optional[ExperimentRun]
if run is not None:
    await run.log_metric("x", 0.1)

# DO NOT — reach into the internal ContextVar
from kailash_ml.tracking.runner import _current_run  # BLOCKED outside tracking package
run = _current_run.get()                              # BLOCKED — internal symbol
```

**Implementation contract**: The internal `ContextVar` lives at `kailash_ml.tracking.runner._current_run: ContextVar[Optional[ExperimentRun]]` as an implementation detail. `km.track()` pushes on `__aenter__` and pops on `__aexit__` via `ContextVar.reset(token)`. Leaked tokens across `await` boundaries are BLOCKED. Exactly one ambient run exists at any depth; nested `km.track()` stacks via token-reset.

Consumers (listed in their spec):

- `km.autolog()` (`ml-autolog.md` §3) — attaches callbacks only when `get_current_run() is not None`.
- `DLDiagnostics(tracker=None)` (`ml-diagnostics.md` §4.1) — reads `get_current_run()` when `tracker is None`.
- `RLDiagnostics(tracker=None)` (`ml-rl-core.md` §7) — same.
- `ModelRegistry.register()` (`ml-registry.md` §6.2) — uses `get_current_run().run_id` as default `tracker_run_id`.
- `MLEngine` + every engine in `ml-engines-v2-addendum §E1.1` — reads `get_current_run()` at mutation entry (E1.2 MUST 1).

**Why:** A public accessor is the stable API surface. Callers that grep `_current_run.get()` in 0.x code MUST migrate to `get_current_run()` at 1.0.0 (see §15 Changelog). The internal ContextVar name may be refactored (e.g. renamed to `_run_ctxvar`, moved under a different sub-module) in any future minor release without breaking any sibling-spec consumer. `rules/orphan-detection.md` §6 applies: `get_current_run` MUST appear in `kailash_ml.tracking.__all__` and be eagerly imported — no lazy `__getattr__`.

### 10.2 Public Accessor — `get_current_tenant_id()`

**MUST**: The public accessor for tenant is `kailash_ml.tracking.get_current_tenant_id() -> Optional[str]`, reading the internal `_current_tenant_id: ContextVar[Optional[str]]` set by `km.track(tenant_id=)`. Every query primitive that defaults `tenant_id=None` to the ambient value MUST go through this accessor.

### 10.3 DDP / FSDP / DeepSpeed Rank-0-Only Emission (Decision 4)

**MUST**: Every mutation primitive on `ExperimentRun` — `log_metric`, `log_metrics`, `log_figure`, `log_artifact`, `log_model`, `log_param`, `log_params`, `set_tags`, `attach_training_result` — MUST emit ONLY when the process is rank-0 under a distributed training setup. Rank-0 is hardcoded, NOT configurable.

```python
# DO — rank-0 gate at every mutation entry
def _is_rank_zero() -> bool:
    try:
        import torch.distributed as dist
        if dist.is_available() and dist.is_initialized():
            return dist.get_rank() == 0
    except (ImportError, RuntimeError):
        pass
    return True  # rank API unavailable → treat as rank-0 (single-process)

async def log_metric(self, key, value, *, step=None, timestamp=None):
    if not _is_rank_zero():
        return   # silent no-op on non-rank-0 workers
    # ... normal path
```

**Why:** Lightning DDP, HF Trainer deepspeed integration, and raw `torch.distributed` launchers all spawn N processes (1 per GPU). Without the rank-0 gate, every metric is written N times, corrupting every dashboard panel and every `log_metrics` row. Rank-0-only is the industry convention (W&B, MLflow Lightning integration, `lightning.pytorch.loggers.*`). Decision 4 locks it as a MUST clause, not an opt-in flag — making it configurable re-introduces the N-duplicate failure mode.

**Tier 2 test**: `tests/integration/test_tracker_ddp_rank0_only_emission.py` MUST mock `torch.distributed.get_rank()` to return 1 on a worker process, call `run.log_metric(...)`, and assert NO row appears in `_kml_metric`. The companion test on rank 0 MUST assert the row DOES appear. Rank-API-unavailable path (non-distributed execution) MUST pass-through normally.

Origin: Decision 4 (approved 2026-04-21). Cross-references: autolog mirror clause (`ml-autolog.md §3.2`), DLDiagnostics mirror clause (`ml-diagnostics.md §4`).

---

## 11. MCP Surface

### 11.1 Server Class

**MUST**: `kailash_ml.tracker.mcp.TrackerMCPServer` MUST exist as a subclass of the `kailash-mcp` framework server base. Per `rules/framework-first.md`, rolling a custom MCP server is BLOCKED.

```python
from kailash_ml.tracker.mcp import TrackerMCPServer
from kailash.mcp import serve_mcp

server = TrackerMCPServer(tracker=my_tracker, registry=my_registry)
await serve_mcp(server, transport="stdio")
```

Origin: closes `round-1-spec-compliance.md:1.12` (grep currently empty).

### 11.2 Tools

**MUST**: The server MUST expose these tools:

| Tool           | Signature                                                               |
| -------------- | ----------------------------------------------------------------------- |
| `start_run`    | `(experiment, tenant_id=None, parent_run_id=None, tags=None) -> run_id` |
| `log_metric`   | `(run_id, key, value, step=None, tenant_id=None) -> None`               |
| `log_params`   | `(run_id, mapping, tenant_id=None) -> None`                             |
| `search_runs`  | `(filter, order_by, limit, tenant_id=None) -> DataFrame(JSON)`          |
| `get_run`      | `(run_id, tenant_id=None) -> RunRecord(JSON)`                           |
| `compare_runs` | `(run_a, run_b, tenant_id=None) -> RunDiff(JSON)`                       |

Every tool MUST be gated by the MCP framework's auth layer; audit rows record the calling agent identity.

---

## 12. Import From MLflow

### 12.1 Entry Point

```python
async def import_mlflow(
    path_or_uri: str,
    *,
    tenant_id: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    model_names: Optional[List[str]] = None,
) -> MigrationReport: ...
```

**MUST**: `import_mlflow` MUST be exposed as `km.import_mlflow(...)`. Supports MLflow URI schemes `http://`, `https://`, `file://`, `sqlite://`, `databricks://`. Idempotent (matched by `source_run_id == MLflow.run_id`). Preserves MLflow stages as kailash-ml aliases (`Production` → `production`, `Staging` → `staging`).

Origin: closes `round-1-spec-compliance.md:1.18`; industry competitive gap (no migration = no adoption from MLflow-installed base).

### 12.2 Re-verification of Pickle Models

**MUST**: For every imported pickle-format model, if an ONNX export is viable, emit a fresh ONNX artifact and set `onnx_reexported=True` on the version. Otherwise set `onnx_status="legacy_pickle_only"`. Silent carry-over of the legacy format is BLOCKED.

---

## 13. Dashboard Contract

### 13.1 Default

**MUST**: `MLDashboard(db_url=None)` MUST default `db_url` to `f"sqlite:///{Path.home() / '.kailash_ml' / 'ml.db'}"`. The default MUST match §2.2 verbatim. Shipping with any other default is BLOCKED.

### 13.2 Streaming Endpoints

**MUST**: Dashboard server MUST expose SSE endpoint `/stream/runs/{run_id}` and WebSocket endpoint `/ws/runs/{run_id}` that push live metric updates. Implementation details are owned by `ml-dashboard.md`; this spec defines only the store-path contract and the event-shape contract (JSON with `type in {"metric","param","status","artifact"}`).

---

## 14. Test Matrix

### 14.1 Unit Tests (Tier 1)

**MUST**: Every public method on `ExperimentTracker`, `ExperimentRun`, `ModelRegistry`, `ArtifactStore`, and `TrackerMCPServer` MUST have at least one Tier 1 unit test exercising the happy path AND one exercising each typed exception (§9.1). Unit tests MAY use `store="sqlite+memory"`.

### 14.2 Wiring Tests (Tier 2)

**MUST**: Every manager-shape class MUST have a `test_<lowercase_name>_wiring.py` file per `rules/facade-manager-detection.md` §2. Required files:

```
packages/kailash-ml/tests/integration/
  test_experimenttracker_wiring.py
  test_modelregistry_wiring.py
  test_artifactstore_wiring.py
  test_trackermcpserver_wiring.py
```

Each wiring test MUST:

1. Import through `km.track()` / `km.registry()` / `km.artifacts()` — NOT the class directly.
2. Run against real Postgres (via the pre-configured Tier 2 fixture).
3. Assert externally-observable effect (row in `_kml_audit`, artifact in S3 test bucket, etc.).

### 14.3 End-to-End Unification Regression

**MUST**: Tier 2 file `tests/regression/test_tracker_dashboard_unification.py` MUST:

1. Start `km.track("e2e")` against the default store.
2. Log one metric.
3. Open `MLDashboard()` with default constructor.
4. Assert the dashboard's `latest()` method returns the run within 1 second.

This is the regression test that closes round-1 T1. Deleting it is BLOCKED.

### 14.4 NaN/Inf Metric Regression

**MUST**: `tests/regression/test_metric_value_error.py` asserts `log_metric("loss", float("nan"))` and `log_metric("loss", float("inf"))` both raise `MetricValueError`.

### 14.5 Tenant Isolation Regression

**MUST**: `tests/regression/test_tenant_isolation_keyspace.py` asserts every key written by `km.track("exp", tenant_id="A")` contains the literal substring `:A:` and keys written with `tenant_id="B"` contain `:B:`; cross-tenant read of `:A:` keys under `tenant_id="B"` raises `RunNotFoundError`.

---

## 15. Changelog — 1.0.0 Breaking Changes (Decision 14)

`kailash-ml 1.0.0` is a MAJOR release (0.17.x → 1.0.0). Every row below is a BREAKING change. The version jump signals API-stable across the full ML lifecycle surface.

| Area                  | Change                                                                                                                                                                                                                                                                                                                           |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tracker class         | **DELETED** — `kailash_ml.tracking.SQLiteTrackerBackend` removed. Use `km.track()` / `await ExperimentTracker.create(...)`. (§2.3, §2.5)                                                                                                                                                                                         |
| Tracker constructor   | **RENAMED** — sole async factory is `await ExperimentTracker.create(store_url=None, *, default_tenant_id=None)`. Legacy `.open()` / `ExperimentTracker(conn)` BLOCKED. (§2.5)                                                                                                                                                    |
| Default DB path       | **UNIFIED** — `km.track()` and `MLDashboard()` both default to `~/.kailash_ml/ml.db`. All 0.x alternate-path stores consolidated via `1_0_0_merge_legacy_stores` migration. (§2.2, §16)                                                                                                                                          |
| Status vocabulary     | **HARD MIGRATION** — `{RUNNING, FINISHED, FAILED, KILLED}` only. 0.x `COMPLETED` / `SUCCESS` rows hard-coerced to `FINISHED` via `1_0_0_rename_status` migration. No accept-on-read bridge. (§3.2, §3.5, §16)                                                                                                                    |
| `log_metric`          | **ADDED** on `ExperimentRun` (was engine-only at 0.x); NaN/Inf raises `MetricValueError`. (§4.2)                                                                                                                                                                                                                                 |
| `log_metrics`         | **ADDED** on `ExperimentRun`. (§4.2)                                                                                                                                                                                                                                                                                             |
| Query return type     | **CHANGED** — `list_runs` / `search_runs` / `list_experiments` / `list_metrics` / `list_artifacts` now return `polars.DataFrame`. `list[Run]` is BLOCKED. (§5.1)                                                                                                                                                                 |
| `diff_runs`           | **ADDED** — new primitive with frozen `RunDiff` dataclass. (§5.3)                                                                                                                                                                                                                                                                |
| Keyspace              | **MIGRATED** — all cache keys to `kailash_ml:v1:{tenant_id}:{resource}:{id}`. (§7.1)                                                                                                                                                                                                                                             |
| Tenant strict mode    | **ENFORCED** — `multi_tenant=True` raises `TenantRequiredError`; silent `"default"` fallback BLOCKED. `"_single"` used in single-tenant dev. (§7.2)                                                                                                                                                                              |
| `actor_id`            | **CONTEXTVAR ONLY** — `actor_id` flows from `km.track(actor_id=...)` session entry, NOT as per-call kwarg on `log_metric` / `log_param` / etc. (HIGH-4 round-1 finding, §8.1)                                                                                                                                                    |
| Audit rows            | **IMMUTABLE** — every mutation writes a row; GDPR erasure does NOT delete audit rows (hashed fingerprints retained per Decision 2). (§8.2, §8.4)                                                                                                                                                                                 |
| Error hierarchy       | **NEW ROOT** — `MLError` is the package root; 11 family errors inherit from `MLError`; every domain-specific error re-routes. (CRIT-3, §9.1)                                                                                                                                                                                     |
| Exceptions            | 15 typed exceptions in the `TrackingError` family (`ActorRequiredError`, `MetricValueError`, `ParamValueError` added; `ParamValueError` mirrors `MetricValueError` multi-inheriting `ValueError`). Cross-cutting `UnsupportedTrainerError` (Decision 8) and `MultiTenantOpError` (Decision 12) sit at the `MLError` root. (§9.1) |
| `sqlite+memory` alias | **ACCEPTED** in `store_url=` parameter. (§6.1)                                                                                                                                                                                                                                                                                   |
| Contextvar public API | **ADDED** — `kailash_ml.tracking.get_current_run()` + `get_current_tenant_id()` public; direct `_current_run` access BLOCKED for library callers. (CRIT-4, §10.1, §10.2)                                                                                                                                                         |
| DDP rank-0 gate       | **HARDCODED** — every mutation emits only when `torch.distributed.get_rank() == 0` OR rank API unavailable. NOT configurable. (Decision 4, §10.3)                                                                                                                                                                                |
| MCP                   | `TrackerMCPServer` added with 6 tools. MCP is the ONLY surface that takes explicit `(run_id, tenant_id, actor_id)` (no contextvar across MCP). (§11)                                                                                                                                                                             |
| MLflow import         | `km.import_mlflow()` added. (§12)                                                                                                                                                                                                                                                                                                |
| `log_figure`          | New primitive for DLDiagnostics / RLDiagnostics event sink. (§4.4)                                                                                                                                                                                                                                                               |
| `km.autolog()`        | New entry point (`ml-autolog.md`).                                                                                                                                                                                                                                                                                               |

### Migration script outline (ships in same PR — Decision 14)

- `kailash_ml.tracking.migrations.1_0_0_rename_status` — coerce SUCCESS/COMPLETED → FINISHED atomically (§16).
- `kailash_ml.tracking.migrations.1_0_0_merge_legacy_stores` — consolidate any existing `~/.kailash_ml/kailash-ml.db` / alternate 0.x store into `~/.kailash_ml/ml.db` (§16).
- `kailash_ml.tracking.migrations.1_0_0_delete_sqlitetrackerbackend` — remove the legacy import alias + namespace surface (§16).

---

## 16. Migration — 0.17.x → 1.0.0

### 16.1 Numbered Migration Inventory

All migrations live under `packages/kailash-ml/src/kailash_ml/_storage/migrations/` per `rules/schema-migration.md`. They run atomically on first `km.track()` / `MLDashboard()` call at 1.0.0 against any pre-1.0 store, in numeric order.

| Migration                               | Operation                                                                                                                                                                                                                                                                        |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `1_0_0_rename_status`                   | `UPDATE _kml_run SET status='FINISHED' WHERE status IN ('COMPLETED', 'SUCCESS', 'SUCCEEDED', 'DONE')` — atomic, single transaction. Add CHECK constraint `status IN ('RUNNING', 'FINISHED', 'FAILED', 'KILLED')` after the coercion.                                             |
| `1_0_0_merge_legacy_stores`             | Detect any existing `~/.kailash_ml/kailash-ml.db` (legacy dashboard default) — copy rows into `~/.kailash_ml/ml.db` resolving `tenant_id` collisions via (tenant_id, run_id) compound PK; rename legacy file to `kailash-ml.db.pre-1.0`. Emit INFO log with row counts migrated. |
| `1_0_0_delete_sqlitetrackerbackend`     | Remove `kailash_ml.tracking.SQLiteTrackerBackend` import alias from `__init__.py`; delete `kailash_ml/tracking/sqlite_backend.py` (file-level delete); update `__all__` to drop the symbol. (Code-level migration, not DDL.)                                                     |
| `1_0_0_add_actor_required_error`        | Register `ActorRequiredError` in `kailash_ml.errors.__all__` + re-export from `kailash_ml/__init__.py`. (Code-level migration.)                                                                                                                                                  |
| `1_0_0_add_contextvar_public_accessors` | Register `get_current_run`, `get_current_tenant_id` in `kailash_ml.tracking.__all__` + eager import per `rules/orphan-detection.md` §6. (Code-level migration.)                                                                                                                  |
| `1_0_0_collapse_keyspace`               | Version-wildcard sweep any cached redis keys `kailash_ml:v0:*` into `kailash_ml:v1:*` per `rules/tenant-isolation.md §3a`. Operators who never enabled Redis cache are no-op.                                                                                                    |

### 16.2 Migration Doc

The migration guide ships in the same PR as the 1.0.0 version bump at `packages/kailash-ml/docs/MIGRATION_1_0_0.md`. It covers:

1. **What's deleted** — `SQLiteTrackerBackend`, `ExperimentTracker(conn)` sync-construction, per-call `tenant_id=` / `actor_id=` kwargs on mutations, `status="COMPLETED"` / `"SUCCESS"` write paths.
2. **What's renamed** — `.open()` → `.create()`, legacy store path → canonical `~/.kailash_ml/ml.db`.
3. **What's new** — `get_current_run()` / `get_current_tenant_id()`, `MLError` root, `log_metric` on ExperimentRun, `diff_runs`, `km.autolog()`, `TrackerMCPServer`.
4. **Code-migration examples** — 10-line before/after sketches for the five most common 0.x usages.
5. **Rollback instructions** — the legacy store is renamed (not deleted) to `kailash-ml.db.pre-1.0`; a user who needs to roll back pins to `kailash-ml<1.0` and points the dashboard at the renamed file.

### 16.3 Migration Tests

**MUST**: `tests/integration/test_migration_1_0_0.py` exercises each numbered migration against a synthetic 0.17.x store:

1. Seed the pre-1.0 store with 100 rows mixing `status='COMPLETED'`, `'SUCCESS'`, `'FINISHED'`.
2. Run the migration suite.
3. Assert every row now has `status='FINISHED'` (no drift).
4. Assert the CHECK constraint rejects a subsequent insert with `status='COMPLETED'`.
5. Repeat for legacy-store merge + alias-deletion tests.

Regression test `tests/regression/test_migration_idempotent.py` ensures running the migration suite twice produces the same result (no duplicate rows, no duplicate errors).

---

## Appendix A. Open Questions

All round-2 open questions are RESOLVED per `workspaces/kailash-ml-audit/04-validate/approved-decisions.md` (2026-04-21). This appendix is retained for traceability only — no open questions remain at 1.0.0.

| Original TBD                    | Disposition                                                                                                                                                                                                                                                                         |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Status vocab migration          | **PINNED** (Decision 1) — FINISHED only; hard-coerce via numbered migration (§16).                                                                                                                                                                                                  |
| GDPR erasure semantics          | **PINNED** (Decision 2) — audit rows immutable; hashed fingerprints (§8.4).                                                                                                                                                                                                         |
| `MetricValueError` inheritance  | **PINNED** (Phase-B Round 2b §A.1 T-03 SAFE-DEFAULT) — `MetricValueError(TrackingError, ValueError)` multi-inherit (§9.1).                                                                                                                                                          |
| Actor-resolution default        | **PINNED** (HIGH-4 round-1 finding) — `require_actor=False` default, flipped True by `multi_tenant=True`; contextvar only, no kwarg (§8.1).                                                                                                                                         |
| `_kml_` vs `kailash_ml_` prefix | **PINNED** (TBD T-02 + Phase-F F1) — keep both: `_kml_` tables (internal tables; leading underscore marks these as not-for-direct-user-query per `rules/dataflow-identifier-safety.md` Rule 2; Postgres 63-char brevity retained); `kailash_ml:` Redis keyspace (operator-visible). |
| Audit-row delete semantics      | **PINNED** (Decision 2) — audit rows NEVER deleted; fingerprints persist.                                                                                                                                                                                                           |
| Cross-SDK status-enum parity    | **PINNED** (Decision 3) — 4-member enum byte-identical kailash-py ↔ kailash-rs; cross-SDK todo at kailash-rs#502.                                                                                                                                                                   |

---

_End of spec. Authored per `rules/specs-authority.md` + `rules/rule-authoring.md` + `rules/tenant-isolation.md` + `rules/facade-manager-detection.md` + `rules/schema-migration.md` + `rules/event-payload-classification.md`. Pinned 2026-04-21 per `workspaces/kailash-ml-audit/04-validate/approved-decisions.md` Decisions 1-14. Closes round-1 findings 1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20 + themes T1 / T6 / T7-H2 + CRIT-1/2/3/4 + HIGH-4/6/8._
