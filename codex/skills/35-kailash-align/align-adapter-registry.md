# Align Adapter Registry

AdapterRegistry manages LoRA adapter versioning, lifecycle stages, adapter chaining (e.g., SFT then DPO), and extends the kailash-ml ModelRegistry pattern for LLM-specific adapter management.

## Setup

```python
from kailash_align.registry import AdapterRegistry

registry = AdapterRegistry(
    storage_path="./adapters",
    max_adapters=10_000,               # Bounded registry (prevents OOM)
    max_versions_per_adapter=1_000,    # Bounded per-adapter
)
await registry.initialize()
```

## Register an Adapter

Adapters are registered after training. AlignmentPipeline registers automatically, but manual registration is also supported.

```python
# Automatic registration (via AlignmentPipeline)
result = await pipeline.train(dataset=dataset, adapter_name="code-dpo-v1")
# result.adapter_id is already registered

# Manual registration
adapter_id = await registry.register(
    name="code-dpo-v1",
    base_model_id="meta-llama/Llama-3.1-8B",
    method="dpo",
    adapter_path="./output/adapter_weights",
    metrics={"win_rate": 0.63, "rouge1": 0.45},
    config=config.to_dict(),          # Training config for reproducibility
    tags={"task": "code-review", "dataset": "code-preferences-v2"},
)
```

## Adapter Lifecycle

Adapters follow a lifecycle similar to ModelRegistry but tailored for LoRA adapters.

```
draft --> evaluated --> active --> archived
  |                      |
  +--- (rejected) -------+--- (rollback to evaluated)
```

| Stage         | Purpose                                 | Transition Trigger   |
| ------------- | --------------------------------------- | -------------------- |
| **draft**     | Just trained, not yet evaluated         | AlignmentPipeline    |
| **evaluated** | Passed evaluation, ready for deployment | AlignmentEvaluator   |
| **active**    | Currently deployed and serving          | Human approval       |
| **archived**  | Retired, kept for reproducibility       | Superseded or manual |

```python
# Lifecycle transitions
await registry.transition(adapter_id, stage="evaluated", eval_result=eval_result)
await registry.transition(adapter_id, stage="active")
await registry.transition(adapter_id, stage="archived")

# Rollback
await registry.transition(adapter_id, stage="evaluated")
```

## Version Tracking

Each adapter name can have multiple versions. Versions are immutable — a new training run creates a new version.

```python
# Version 1
result_v1 = await pipeline.train(dataset=dataset_v1, adapter_name="code-dpo")
# Registered as code-dpo v1

# Version 2 (same name, new training)
result_v2 = await pipeline.train(dataset=dataset_v2, adapter_name="code-dpo")
# Registered as code-dpo v2

# Query versions
versions = await registry.list_versions("code-dpo")
# [AdapterInfo(name="code-dpo", version=1, ...), AdapterInfo(name="code-dpo", version=2, ...)]

# Get specific version
adapter_v1 = await registry.get("code-dpo", version=1)

# Get latest version
latest = await registry.get_latest("code-dpo")

# Get latest active version
active = await registry.get_latest("code-dpo", stage="active")
```

## Adapter Chaining

Chain multiple adapters sequentially. The primary use case is `sft_then_dpo`: train SFT first, then apply DPO on top of the SFT adapter.

```python
# Step 1: SFT training
sft_config = AlignmentConfig(method="sft", base_model_id="meta-llama/Llama-3.1-8B")
sft_pipeline = AlignmentPipeline(config=sft_config)
sft_result = await sft_pipeline.train(dataset=sft_dataset, adapter_name="code-sft")

# Step 2: DPO on top of SFT
dpo_config = AlignmentConfig(
    method="dpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    parent_adapter_id=sft_result.adapter_id,  # Chain from SFT
)
dpo_pipeline = AlignmentPipeline(config=dpo_config)
dpo_result = await dpo_pipeline.train(dataset=preference_dataset, adapter_name="code-dpo")

# Registry tracks the chain
chain = await registry.get_chain(dpo_result.adapter_id)
# chain = [sft_result.adapter_id, dpo_result.adapter_id]
```

### Automatic Chaining with sft_then_dpo

The `sft_then_dpo` method automates the two-stage process.

```python
config = AlignmentConfig(
    method="sft_then_dpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    sft=SFTConfig(num_train_epochs=1),
    dpo=DPOConfig(beta=0.1),
)

pipeline = AlignmentPipeline(config=config)
result = await pipeline.train(
    dataset={"sft": sft_dataset, "dpo": preference_dataset},
    adapter_name="code-aligned",
)
# result.adapter_id points to the final DPO adapter
# result.chain = [sft_adapter_id, dpo_adapter_id]
# Both adapters registered in AdapterRegistry with parent relationship
```

## Query and Search

```python
# List all adapters
adapters = await registry.list_adapters()

# Filter by base model
adapters = await registry.list_adapters(base_model_id="meta-llama/Llama-3.1-8B")

# Filter by method
adapters = await registry.list_adapters(method="dpo")

# Filter by stage
active_adapters = await registry.list_adapters(stage="active")

# Search by tags
code_adapters = await registry.search(tags={"task": "code-review"})

# Filter by metrics
good_adapters = await registry.search(min_metrics={"win_rate": 0.55})
```

## Adapter Metadata

```python
adapter = await registry.get(adapter_id)

adapter.name                # "code-dpo"
adapter.version             # 2
adapter.base_model_id       # "meta-llama/Llama-3.1-8B"
adapter.method              # "dpo"
adapter.stage               # "active"
adapter.metrics             # {"win_rate": 0.63, "rouge1": 0.45}
adapter.config              # Full training config dict
adapter.tags                # {"task": "code-review", "dataset": "code-preferences-v2"}
adapter.parent_adapter_id   # SFT adapter ID if chained, None otherwise
adapter.created_at          # Timestamp
adapter.adapter_path        # Path to adapter weights
```

## Extends ModelRegistry

AdapterRegistry follows the same patterns as kailash-ml's ModelRegistry:

- Bounded storage to prevent OOM (`max_adapters`, `max_versions_per_adapter`)
- Exceeding bounds raises `RegistryCapacityError`
- Immutable versions — no in-place modification
- Full audit trail of stage transitions

The key differences from ModelRegistry:

- Tracks LoRA-specific metadata (rank, alpha, target modules)
- Supports adapter chaining (parent-child relationships)
- Lifecycle stages are `draft/evaluated/active/archived` (not `staging/shadow/production/archived`)
- Integrates with AlignmentEvaluator for the `draft -> evaluated` transition

## Bounded Registry (Security)

Registries are bounded to prevent unbounded growth leading to OOM.

```python
registry = AdapterRegistry(
    storage_path="./adapters",
    max_adapters=10_000,               # Total adapter names
    max_versions_per_adapter=1_000,    # Versions per name
)

# Exceeding capacity raises RegistryCapacityError
try:
    await registry.register(name="overflow-adapter", ...)
except RegistryCapacityError:
    # Clean up old archived adapters first
    await registry.cleanup(stage="archived", keep_latest=5)
```

## Critical Rules

- Adapters are immutable once registered — new training creates new versions
- Adapter chaining tracks parent-child relationships for full lineage
- `draft -> evaluated` requires an eval_result from AlignmentEvaluator
- `evaluated -> active` requires human approval (unless auto_approve=True)
- Bounded registries prevent OOM — `RegistryCapacityError` on overflow
- Archived adapters are never deleted automatically — kept for reproducibility
- All adapter metadata (config, metrics, tags) stored for full reproducibility
