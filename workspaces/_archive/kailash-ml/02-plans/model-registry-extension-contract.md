# ModelRegistry Extension Contract

**Status**: Frozen (Phase 0)
**Consumers**: ML-201 (ModelRegistry implementation), kailash-align (AdapterRegistry)
**Date**: 2026-04-01

## Purpose

This document defines the frozen public API of `ModelRegistry` that `AdapterRegistry` (in kailash-align) extends via class inheritance. Any change to these surfaces breaks AdapterRegistry. This contract is published before implementation begins to enable parallel development.

## Dependency Relationship

```
kailash-align.AdapterRegistry(ModelRegistry)
    ├── calls super().register_model()
    ├── overrides get_model()
    ├── accesses self._db (shared DataFlow instance)
    └── creates additional DataFlow models (AlignAdapter, AlignAdapterVersion)
```

## Constructor

```python
class ModelRegistry:
    def __init__(
        self,
        db: DataFlow,
        artifact_store: ArtifactStore | None = None,
        *,
        auto_migrate: bool = True,
    ) -> None:
        """
        Args:
            db: DataFlow instance for model metadata storage.
            artifact_store: Where model files are stored. Defaults to LocalFileArtifactStore.
            auto_migrate: Create DataFlow tables on init if they don't exist.
        """
```

### Internal Access

- `self._db: DataFlow` -- The DataFlow instance. AdapterRegistry accesses this to create additional models (`AlignAdapter`, `AlignAdapterVersion`) using the same database connection.
- `self._artifact_store: ArtifactStore` -- The resolved artifact store instance.

## Frozen Public Methods (5)

### 1. register_model

```python
async def register_model(
    self,
    name: str,
    artifact_path: str | Path,
    *,
    metrics: list[MetricSpec] | None = None,
    signature: ModelSignature | None = None,
    tags: dict[str, str] | None = None,
    stage: str = "staging",  # "staging", "shadow", "production", "archived"
) -> ModelVersion:
    """Register a new model version. Returns the created ModelVersion.

    Behavior:
    - Creates MLModel row if name doesn't exist yet
    - Auto-increments version number per model name
    - Stores artifact via artifact_store
    - Records metrics and signature as JSON
    - Returns the created ModelVersion with all fields populated
    """
```

### 2. get_model

```python
async def get_model(
    self,
    name: str,
    version: int | None = None,
    *,
    stage: str | None = None,
) -> ModelVersion:
    """Load a model version.

    Behavior:
    - If version is given, returns that specific version
    - If version is None and stage is given, returns latest version at that stage
    - If both are None, returns latest version regardless of stage
    - Raises ModelNotFoundError if not found
    """
```

### 3. list_models

```python
async def list_models(
    self,
    *,
    stage: str | None = None,
    tags: dict[str, str] | None = None,
    limit: int = 100,
) -> list[ModelInfo]:
    """List registered models with optional filtering.

    Behavior:
    - Returns ModelInfo (name, description, latest_version, latest_stage, tags)
    - Filters by stage if given (any version at that stage)
    - Filters by tags if given (all tags must match)
    - Ordered by most recently updated first
    """
```

### 4. promote_model

```python
async def promote_model(
    self,
    name: str,
    version: int,
    target_stage: str,
) -> ModelVersion:
    """Promote a model version to a new stage.

    Behavior:
    - Updates the version's stage field
    - Records transition in MLModelTransition table (audit trail)
    - Returns the updated ModelVersion
    - Raises ModelNotFoundError if name/version doesn't exist
    """
```

### 5. get_model_versions

```python
async def get_model_versions(
    self,
    name: str,
    *,
    limit: int = 50,
) -> list[ModelVersion]:
    """List all versions of a named model, newest first.

    Behavior:
    - Returns list of ModelVersion ordered by version descending
    - Raises ModelNotFoundError if model name doesn't exist
    """
```

## DataFlow Model Schemas

### MLModel -- one row per model name

```python
@db.model
class MLModel:
    id: str          # UUID
    name: str        # unique model name
    description: str
    created_at: datetime
    updated_at: datetime
    tags: dict       # JSON
```

### MLModelVersion -- one row per model version

```python
@db.model
class MLModelVersion:
    id: str                 # UUID
    model_id: str           # FK -> MLModel.id
    version: int            # auto-incrementing per model
    stage: str              # "staging" | "shadow" | "production" | "archived"
    artifact_path: str      # path in artifact store
    metrics: dict           # JSON: list of MetricSpec.to_dict()
    signature: dict         # JSON: ModelSignature.to_dict()
    onnx_status: str        # "pending" | "success" | "failed" | "not_applicable"
    onnx_error: str | None  # error message if onnx_status == "failed"
    model_metadata: dict    # JSON: model_metadata.json content
    created_at: datetime
    tags: dict              # JSON
```

### MLModelTransition -- audit trail for stage changes

```python
@db.model
class MLModelTransition:
    id: str
    model_version_id: str  # FK -> MLModelVersion.id
    from_stage: str
    to_stage: str
    transitioned_at: datetime
    reason: str | None
```

## Extension Points for AdapterRegistry

| Method                 | AdapterRegistry Usage                                                                                              | Access Pattern  |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------- |
| `register_model()`     | Calls `super().register_model()` then adds adapter-specific fields (lora_config, base_model_id)                    | Extension       |
| `get_model()`          | Wraps result with adapter-specific fields                                                                          | Extension       |
| `list_models()`        | Filters by adapter type tag                                                                                        | Extension       |
| `promote_model()`      | Inherited directly                                                                                                 | Inherited       |
| `get_model_versions()` | Inherited directly                                                                                                 | Inherited       |
| `self._db`             | AdapterRegistry creates additional DataFlow models (`AlignAdapter`, `AlignAdapterVersion`) using the same instance | Internal access |

## Anti-Features (R1-06, R2-03)

ModelRegistry MUST NOT:

1. **Implement experiment tracking** -- MLflow/W&B territory. ModelRegistry stores model versions, not training runs.
2. **Implement artifact logging beyond model files** -- No log files, no datasets, no plots. Just model artifacts.
3. **Implement model deployment management** -- InferenceServer's job. ModelRegistry stores metadata; InferenceServer loads and serves.
4. **Provide a UI or dashboard** -- Registry is an API. Visualization is a consumer concern.
5. **Require or interface with a running MLflow server** -- File format only. ModelRegistry reads/writes MLflow-compatible directory structures but never calls an MLflow server.
6. **Grow a model comparison UI** -- Comparison logic belongs in DataExplorer or a consumer application.
7. **Track training runs or hyperparameter search history** -- TrainingPipeline's job. ModelRegistry receives the final artifact; it does not track the journey.
