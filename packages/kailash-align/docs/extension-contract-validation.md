# Extension Contract Validation: AdapterRegistry -> ModelRegistry

## Summary

This document validates how `kailash-align`'s `AdapterRegistry` uses `kailash-ml`'s `ModelRegistry` frozen API per the extension contract defined in the kailash-ml workspace.

## Decision: Composition Over Inheritance

**AdapterRegistry uses composition (HAS-A ModelRegistry), not inheritance (IS-A ModelRegistry).**

### Rationale

1. **DataFlow model independence**: AlignAdapter and AlignAdapterVersion are standalone records, not inheriting from MLModel/MLModelVersion. DataFlow cross-package model inheritance is unverified and unnecessary for our use case.

2. **Decoupled evolution**: If ModelRegistry gains new methods or changes its internal model schema, AdapterRegistry is unaffected unless it explicitly delegates to those methods.

3. **Separate personas**: Classical ML models (regression, classification) and LoRA adapters serve different users. Mixing them in a single registry query would confuse both personas.

4. **Risk reduction**: No dependency on ModelRegistry's internal state or lifecycle. AdapterRegistry can function standalone or with a ModelRegistry reference for cross-lookups.

### Trade-off

Adapters are NOT visible via `model_registry.list()`. Users querying ModelRegistry will not see alignment adapters. This is acceptable because:

- Different tools, different workflows, different users
- Cross-registry lookups are available via the optional `model_registry` parameter
- A unified view can be built at a higher level if needed

## Extension Surface Analysis

The extension contract (kailash-ml `docs/extension-contract.md`) defines 7 touch points. Here is how AdapterRegistry uses each:

| Touch Point                                         | Contract Status       | AdapterRegistry Usage                                                                                                                                                                |
| --------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `register(name, artifact, metrics, feature_schema)` | Available in contract | **Not used directly**. AdapterRegistry manages its own records via in-memory store (future: DataFlow Express). Composition means no `super().register()`.                            |
| `promote(name, version, stage)`                     | Available in contract | **Not used directly**. AdapterRegistry implements its own `promote()` with alignment-specific stage validation.                                                                      |
| `load(name, version, stage)`                        | Available in contract | **Used optionally** via `self._model_registry.load()` for loading base model references when cross-registry lookup is needed.                                                        |
| `MLModel` DataFlow model                            | Available in contract | **Not extended**. AlignAdapter is a standalone model with its own schema.                                                                                                            |
| `MLModelVersion` DataFlow model                     | Available in contract | **Not extended**. AlignAdapterVersion is standalone.                                                                                                                                 |
| `ArtifactStore` protocol                            | Available in contract | **Not used yet**. Future: adapter weight storage could use ArtifactStore if the protocol stabilizes. Currently uses filesystem paths.                                                |
| `Stage` enum                                        | Available in contract | **Aligned semantically**. AdapterRegistry uses the same stage names (staging, shadow, production, archived) as strings for now. Will import Stage enum when ModelRegistry is stable. |

## Gaps Identified

1. **ModelRegistry is not yet implemented** (ML-201 pending). AdapterRegistry uses an in-memory store and will integrate with DataFlow Express when the infrastructure is available. This is not a blocker -- the composition pattern means AdapterRegistry is fully functional standalone.

2. **Stage enum**: Currently using string literals matching the contract's Stage values. When ModelRegistry ships the Stage enum, AdapterRegistry should import and use it for type safety.

3. **ArtifactStore protocol**: Not consumed yet. Adapter weights are stored as filesystem paths. When ArtifactStore stabilizes, a future ALN todo should add ArtifactStore integration for adapter weight management.

## DataFlow Model Definitions

### AlignAdapter

Standalone model tracking the adapter identity:

- `id`, `name`, `model_type` (always "alignment")
- `base_model_id`, `base_model_revision` (HuggingFace model reference)
- `lora_config_json` (LoRA parameters as JSON)
- `training_data_ref`, `tags_json`
- `onnx_status` (always "not_applicable" for LLM adapters)
- `created_at`

### AlignAdapterVersion

Standalone model tracking each adapter version:

- `id`, `adapter_id` (FK to AlignAdapter)
- `version`, `stage`
- `adapter_path`, `base_model_id`
- `lora_config_json`, `training_metrics_json`
- `merge_status` (separate/merged/exported)
- `merged_model_path`, `gguf_path`, `quantization_config_json`, `eval_results_json`
- `created_at`

### AdapterSignature

Frozen dataclass (separate from ModelSignature per R2):

- `base_model_id`, `adapter_type` (lora/qlora)
- `rank`, `alpha`, `target_modules`
- `task_type` (CAUSAL_LM), `training_method` (sft/dpo/sft_then_dpo)

## Validation Verdict

**The extension contract covers AdapterRegistry's needs.** The composition pattern means AdapterRegistry does not require ModelRegistry to be implemented -- it uses its own storage and lifecycle management. When ModelRegistry ships (ML-201), the optional `model_registry` parameter enables cross-registry lookups without any AdapterRegistry code changes.

No coordination ticket needed for kailash-ml. The contract is sufficient as-is for the composition approach.
