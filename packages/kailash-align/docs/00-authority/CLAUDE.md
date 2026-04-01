# kailash-align -- Agent Instructions

Preloaded context for AI agents working with the `kailash-align` package. This file is the authoritative reference for package architecture, supported methods, and development constraints.

## Package Purpose

`kailash-align` is an LLM fine-tuning and alignment framework that wraps TRL (Transformer Reinforcement Learning). It provides a unified `AlignmentPipeline` interface over 12 alignment methods, with LoRA/QLoRA adapter management, reward function registries, GPU memory estimation, evaluation via lm-eval-harness, and serving pipelines (GGUF export, Ollama, vLLM).

The framework value is orchestration, not training innovation. TRL does the training. kailash-align provides: config management, adapter registry integration, checkpoint resumption, method dispatch via `MethodRegistry`, and security-hardened reward function handling.

## Architecture

```
AlignmentConfig
    |
    +-- LoRAConfig (rank, alpha, target_modules, dropout)
    +-- SFTConfig / DPOConfig / KTOConfig / ORPOConfig / GRPOConfig / RLOOConfig / OnlineDPOConfig
    |
    v
AlignmentPipeline
    |
    +-- MethodRegistry.get_method(config.method) --> MethodConfig
    |       |
    |       +-- trainer_module + trainer_class_name (lazy import to TRL)
    |       +-- dataset_validator (validates dataset columns)
    |       +-- metrics_extractor (extracts method-specific metrics)
    |       +-- flags: requires_preference_data, requires_reward_func, requires_generation_backend
    |
    +-- RewardRegistry (for online methods: GRPO, RLOO, XPO, NashMD)
    |       |
    |       +-- Named reward functions registered programmatically
    |       +-- Built-in: exact_match, contains_answer, length_penalty
    |
    +-- VLLMBackend / HFGenerationBackend (for online rollout generation)
    |
    v
AlignmentResult
    +-- adapter_name, adapter_path, adapter_version
    +-- training_metrics, experiment_dir, method
```

### Flow

1. User creates `AlignmentConfig` with method name, base model, LoRA config, and method-specific config
2. `AlignmentPipeline.__init__` accepts the config and optional `AdapterRegistry`
3. `pipeline.train(dataset, adapter_name)` dispatches to `MethodRegistry`
4. MethodRegistry resolves the TRL trainer class via lazy import (avoids loading all TRL trainers at module load time)
5. Pipeline loads model, applies LoRA, creates TRL trainer, trains, saves adapter
6. If `AdapterRegistry` is provided, registers the trained adapter with signature and metrics
7. Returns `AlignmentResult` with paths, metrics, and adapter version

## Supported Methods (12)

### Offline Preference (category: "offline")

| Method  | TRL Trainer  | Data Format            | Config Class              |
| ------- | ------------ | ---------------------- | ------------------------- |
| **sft** | `SFTTrainer` | text column            | `SFTConfig`               |
| **dpo** | `DPOTrainer` | prompt/chosen/rejected | `DPOConfig`               |
| **cpo** | `CPOTrainer` | prompt/chosen/rejected | falls back to `SFTConfig` |

DPO supports `loss_type` variants: `ipo`, `simpo`, `robust`, `bco_pair`, `sppo_hard`, `aot`, `aot_pair`, and more (see TRL docs). Set via `AlignmentConfig.loss_type`.

### Unpaired Feedback (category: "unpaired")

| Method  | TRL Trainer  | Data Format             | Config Class              |
| ------- | ------------ | ----------------------- | ------------------------- |
| **kto** | `KTOTrainer` | prompt/completion/label | `KTOConfig`               |
| **bco** | `BCOTrainer` | prompt/completion/label | falls back to `SFTConfig` |

KTO and BCO use binary labels (True/False or 1/0) instead of paired preferences. This dramatically lowers the data collection barrier.

### Monolithic (category: "monolithic")

| Method   | TRL Trainer   | Data Format            | Config Class |
| -------- | ------------- | ---------------------- | ------------ |
| **orpo** | `ORPOTrainer` | prompt/chosen/rejected | `ORPOConfig` |

ORPO combines SFT and preference alignment in a single training pass. Eliminates the need for `sft_then_dpo`.

### Online RL (category: "online")

| Method         | TRL Trainer        | Data Format | Config Class              | Reward Required        |
| -------------- | ------------------ | ----------- | ------------------------- | ---------------------- |
| **grpo**       | `GRPOTrainer`      | prompt      | `GRPOConfig`              | Yes                    |
| **rloo**       | `RLOOTrainer`      | prompt      | `RLOOConfig`              | Yes                    |
| **online_dpo** | `OnlineDPOTrainer` | prompt      | `OnlineDPOConfig`         | No (uses reward model) |
| **xpo**        | `XPOTrainer`       | prompt      | falls back to `SFTConfig` | Yes                    |
| **nash_md**    | `NashMDTrainer`    | prompt      | falls back to `SFTConfig` | Yes                    |

Online methods generate completions at training time and score them. GRPO and RLOO require reward functions from `RewardRegistry`. All online methods support optional vLLM for fast generation.

### Pipeline Combo

| Method           | Description                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| **sft_then_dpo** | Two-stage: SFT on instruction data, then DPO on preference data. The SFT adapter is merged before DPO stage. |

## Key Classes

### Core

- **`AlignmentConfig`** -- Top-level config. Contains `method`, `base_model_id`, `LoRAConfig`, method-specific configs, `loss_type`, `reward_funcs`, `use_qlora`, `experiment_dir`.
- **`AlignmentPipeline`** -- Orchestrates training. Takes `AlignmentConfig` and optional `AdapterRegistry`. Call `await pipeline.train(dataset, adapter_name)`.
- **`AlignmentResult`** -- Returned by `train()`. Contains `adapter_name`, `adapter_path`, `adapter_version`, `training_metrics`, `experiment_dir`, `method`.

### Config Hierarchy

- **`LoRAConfig`** -- LoRA adapter parameters: `rank`, `alpha`, `target_modules`, `dropout`, `bias`. Converts to `peft.LoraConfig` via `to_peft_config()`.
- **`SFTConfig`** -- SFT training: `num_train_epochs`, `per_device_train_batch_size`, `learning_rate`, `max_seq_length`, etc.
- **`DPOConfig`** -- DPO training: adds `beta`, `max_length`, `max_prompt_length`.
- **`KTOConfig`** -- KTO training: adds `desirable_weight`, `undesirable_weight`.
- **`ORPOConfig`** -- ORPO training: adds `beta`, `max_length`, `max_prompt_length`.
- **`GRPOConfig`** -- GRPO training: adds `num_generations`, `temperature`, `max_completion_length`, `kl_coef`, `use_vllm`.
- **`RLOOConfig`** -- RLOO training: same fields as GRPOConfig.
- **`OnlineDPOConfig`** -- Online DPO: adds `beta`, `max_completion_length`, `use_vllm`.

All method configs are `@dataclass(frozen=True)` with `__post_init__` validation (NaN/Inf checks, range checks). Each provides `to_trl_config(output_dir)` to convert to TRL's native config class.

### Registry

- **`MethodRegistry`** (`METHOD_REGISTRY` dict) -- Maps method names to `MethodConfig` objects. Extensible: call `register_method(MethodConfig(...))` to add new methods. Uses lazy string-based references to TRL trainer classes (avoids importing TRL at module load time).
- **`RewardRegistry`** (`reward_registry` singleton) -- Named reward function registry. Functions registered via `@reward_registry.register("name")` decorator or `reward_registry.register_function("name", func)`. Config files reference rewards by name only.

### GPU Memory

- **`GPUMemoryEstimate`** -- Memory breakdown: `model_memory_gb`, `adapter_memory_gb`, `optimizer_memory_gb`, `gradient_memory_gb`, `activation_memory_gb`, `total_estimate_gb`, `recommended_batch_size`, `fits_in_memory`, `notes`.
- **`estimate_training_memory(model_id, ...)`** -- Estimates VRAM requirements. Detects GPU automatically (CUDA, MPS, or manual). Adds 20% safety margin. Accounts for online method overhead.

### Generation Backends

- **`GenerationBackend`** -- Abstract base. Subclasses implement `batch_generate(prompts, ...)`.
- **`VLLMBackend`** -- Fast batch generation via vLLM. Requires CUDA. Install: `pip install kailash-align[online]`.
- **`HFGenerationBackend`** -- Fallback using `transformers.generate()`. Works on CUDA, MPS, and CPU. Slower but universal.

### Evaluation and Serving

- **`AlignmentEvaluator`** -- Wraps lm-eval-harness. Quick preset (3 tasks, ~5 min) and standard preset (6 tasks, ~30-60 min). Requires `pip install kailash-align[eval]`.
- **`AlignmentServing`** -- GGUF export, Ollama deployment, vLLM serving. Requires `pip install kailash-align[serve]`.
- **`AdapterMerger`** -- Merge LoRA adapter into base model. Required before GGUF export.
- **`KaizenModelBridge`** -- Connect fine-tuned models to Kaizen Delegate for agent workflows.
- **`OnPremModelCache`** -- Air-gapped model preparation. CLI: `kailash-align-prepare`.

## Security Constraints

### Reward Functions (CRITICAL)

Reward functions are arbitrary Python callables. They are security-critical because they execute during training.

- Reward functions are **registry-based only**. Register programmatically in Python code.
- **NO pickle** -- Never serialize/deserialize reward functions.
- **NO dynamic import** -- Never resolve reward functions from user-provided module strings.
- **NO eval/exec** -- Never construct reward functions from strings.
- Config files reference rewards by **name only** (string key into `RewardRegistry`).
- `RewardRegistry` is in-process only (not distributed, not persisted).

### Numeric Validation

All config dataclasses validate numeric fields with `math.isfinite()` in `__post_init__`. This prevents NaN/Inf from entering training configs (mirrors trust-plane-security patterns).

### Model Loading

- `trust_remote_code=False` is hardcoded for all model and tokenizer loading calls.
- `local_files_only` flag on `AlignmentConfig` enables air-gapped operation.

## Dependencies

### Required (installed with `pip install kailash-align`)

| Package          | Version       | Purpose                                                  |
| ---------------- | ------------- | -------------------------------------------------------- |
| `torch`          | `>=2.2,<3.0`  | PyTorch runtime                                          |
| `transformers`   | `>=4.40,<5.0` | Model loading, tokenizers                                |
| `trl`            | `>=1.0,<2.0`  | All TRL trainers (SFT, DPO, KTO, ORPO, GRPO, RLOO, etc.) |
| `peft`           | `>=0.10,<1.0` | LoRA/QLoRA adapter management                            |
| `accelerate`     | `>=1.4,<2.0`  | Distributed training, mixed precision                    |
| `datasets`       | `>=3.0,<4.0`  | HuggingFace dataset loading                              |
| `kailash`        | `>=0.4.0`     | Core SDK (workflow runtime)                              |
| `kailash-ml`     | `>=0.1.0`     | ModelRegistry, ML lifecycle                              |
| `kailash-kaizen` | `>=0.3.0`     | Agent framework (for KaizenModelBridge)                  |

### Optional Extras

| Extra      | Command                             | Packages                              | Purpose                                   |
| ---------- | ----------------------------------- | ------------------------------------- | ----------------------------------------- |
| `[rlhf]`   | `pip install kailash-align[rlhf]`   | `bitsandbytes>=0.43`                  | QLoRA 4-bit quantization                  |
| `[eval]`   | `pip install kailash-align[eval]`   | `lm-eval>=0.4`                        | lm-eval-harness benchmarking              |
| `[serve]`  | `pip install kailash-align[serve]`  | `llama-cpp-python>=0.3`, `gguf>=0.10` | GGUF export, Ollama deployment            |
| `[online]` | `pip install kailash-align[online]` | `vllm>=0.6`                           | Fast generation for GRPO/RLOO (CUDA only) |
| `[full]`   | `pip install kailash-align[full]`   | All of the above                      | Everything                                |

## Development Patterns

### Adding a New Training Method

1. Create a `MethodConfig` with the TRL trainer class reference (string-based lazy import).
2. Call `register_method(MethodConfig(...))` in `method_registry.py`.
3. If the method needs a dedicated config class, add it to `config.py` as a `@dataclass(frozen=True)` with `to_trl_config()`.
4. Add the config field to `AlignmentConfig` and wire it in `get_method_config()`.
5. Write dataset validator and metrics extractor functions.

### Lazy Imports

kailash-align uses lazy imports extensively. `__init__.py` uses `__getattr__` to defer all imports. TRL trainer classes are referenced by string in `MethodConfig` and resolved via `_lazy_import()` only at train time. This ensures `import kailash_align` is fast and does not require torch/transformers to be installed for config-only usage.

### Config Validation

All config dataclasses are `frozen=True`. Validation happens in `__post_init__`. Use `_validate_finite()` and `_validate_positive()` helpers for numeric fields. Never allow NaN or Inf through validation.

## File Map

```
src/kailash_align/
    __init__.py          # Lazy imports, __all__
    _version.py          # __version__
    config.py            # AlignmentConfig, LoRAConfig, all method configs
    pipeline.py          # AlignmentPipeline, AlignmentResult
    method_registry.py   # MethodRegistry, METHOD_REGISTRY, MethodConfig
    rewards.py           # RewardRegistry, RewardFunction protocol, built-in rewards
    registry.py          # AdapterRegistry (adapter version tracking)
    gpu_memory.py        # GPUMemoryEstimate, estimate_training_memory
    vllm_backend.py      # VLLMBackend, HFGenerationBackend, GenerationBackend
    evaluator.py         # AlignmentEvaluator, EvalResult, TaskResult
    serving.py           # AlignmentServing, GGUF export, Ollama, vLLM serving
    merge.py             # AdapterMerger (LoRA merge into base model)
    bridge.py            # KaizenModelBridge, BridgeConfig
    onprem.py            # OnPremModelCache, air-gapped preparation
    cli.py               # CLI entry point (kailash-align-prepare)
    models.py            # Data models
    exceptions.py        # AlignmentError, TrainingError hierarchy
```
