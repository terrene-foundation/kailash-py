# Kailash Align Training Specification

Parent domain: LLM fine-tuning / alignment (`kailash-align`). Companion file: `alignment-serving.md`.

Domain truth document for `kailash-align` -- the LLM fine-tuning and alignment framework for the Kailash platform. Version 0.3.1, Apache-2.0, owned by the Terrene Foundation.

Package: `pip install kailash-align`

This file specifies the **training side** of kailash-align: architecture, configuration dataclasses, method registry, AlignmentPipeline orchestrator, training methods (SFT/DPO/KTO/ORPO/GRPO/RLOO/OnlineDPO/experimental), reward functions and registry, GPU memory estimation, and dataset handling. For adapter registry, merging, model serving (GGUF/Ollama/vLLM), generation backends, evaluation, Kaizen bridge, on-prem caching, advisory agents, and serving-side constraints, see `alignment-serving.md`.

---

## 1. Architecture Overview

Kailash Align wraps HuggingFace TRL, PEFT, and transformers into a registry-driven pipeline that tracks adapters through their full lifecycle: training, evaluation, merge, GGUF export, and deployment. The framework value is orchestration, reproducibility, and adapter lifecycle management -- not training innovation.

### 1.1 Module Map

```
kailash_align/
  __init__.py           Lazy-import facade (no torch/transformers at import time)
  _version.py           Version string
  config.py             All configuration dataclasses (frozen, validated)
  pipeline.py           AlignmentPipeline (training orchestrator)
  method_registry.py    MethodRegistry (registry-driven method dispatch)
  registry.py           AdapterRegistry (adapter lifecycle tracking)
  rewards.py            RewardRegistry + RewardFunction protocol
  evaluator.py          AlignmentEvaluator (lm-eval + custom eval)
  serving.py            AlignmentServing (GGUF export, Ollama, vLLM config)
  vllm_backend.py       GenerationBackend ABC, VLLMBackend, HFGenerationBackend
  merge.py              AdapterMerger (LoRA merge into base model)
  gpu_memory.py         GPU memory estimation
  onprem.py             OnPremModelCache + OnPremSetupGuide
  bridge.py             KaizenModelBridge (Align -> Kaizen Delegate)
  models.py             DataFlow field definitions for adapter records
  exceptions.py         Exception hierarchy
  cli.py                kailash-align-prepare CLI
  agents/
    __init__.py          Lazy-import facade for agents
    orchestrator.py      alignment_workflow() convenience function
    strategist.py        AlignmentStrategistAgent (method selection)
    data_curation.py     DataCurationAgent (dataset quality)
    training_config.py   TrainingConfigAgent (hyperparameter selection)
    eval_interpreter.py  EvalInterpreterAgent (results interpretation)
    tools.py             Dumb data endpoint tools for agents
```

### 1.2 Dependency Architecture

**Core dependencies** (always installed):

| Package          | Min Version | Purpose                                  |
| ---------------- | ----------- | ---------------------------------------- |
| `kailash`        | >=0.4.0     | Core SDK                                 |
| `kailash-ml`     | >=0.1.0     | ModelRegistry composition target         |
| `kailash-kaizen` | >=0.3.0     | Agent framework for advisory agents      |
| `torch`          | >=2.2       | Tensor computation                       |
| `transformers`   | >=4.40      | Model loading, tokenizers                |
| `trl`            | >=1.0       | All trainers (SFT, DPO, KTO, GRPO, etc.) |
| `peft`           | >=0.10      | LoRA/QLoRA adapter management            |
| `accelerate`     | >=1.4       | Distributed training, device_map         |
| `datasets`       | >=4.0       | HuggingFace Dataset handling             |
| `click`          | >=8.0       | CLI framework                            |
| `httpx`          | >=0.27      | Async HTTP for bridge/discovery          |

**Optional extras:**

| Extra      | Packages                              | Purpose                             |
| ---------- | ------------------------------------- | ----------------------------------- |
| `[rlhf]`   | `bitsandbytes>=0.43`                  | QLoRA 4-bit quantization            |
| `[eval]`   | `lm-eval>=0.4`                        | Standard benchmark evaluation       |
| `[serve]`  | `llama-cpp-python>=0.3`, `gguf>=0.10` | GGUF conversion and quantization    |
| `[online]` | `vllm>=0.6`                           | vLLM generation backend (CUDA only) |
| `[all]`    | All of the above                      | Everything                          |

### 1.3 Lazy Import Contract

The top-level `__init__.py` uses `__getattr__` to defer all imports. Importing `kailash_align` does NOT load torch, transformers, trl, or peft. Classes are imported on first attribute access. This is critical for CLI startup time and environments where torch is not yet installed.

### 1.4 Exception Hierarchy

```
AlignmentError (base)
  AdapterNotFoundError      Adapter or version not in registry
  TrainingError              Training failure (dataset validation, trainer crash)
  ServingError               Serving operations (GGUF, Ollama, vLLM)
    GGUFConversionError      GGUF conversion or validation failure
    OllamaNotAvailableError  Ollama CLI missing or server not running
  EvaluationError            Benchmark or custom eval failure
  CacheNotFoundError         Model not in on-prem cache
  MergeError                 Adapter merge failure
```

All exceptions inherit from `AlignmentError`. Code that catches Align errors should catch `AlignmentError` for the broad case or the specific subclass for targeted handling.

---

## 2. Configuration System

All configuration is via frozen dataclasses with `__post_init__` validation. No configuration file parsing exists -- users construct dataclasses in Python. Every numeric parameter is validated for finiteness (no NaN, no Inf). Mutually exclusive flags (bf16 vs fp16) are checked at construction time.

### 2.1 LoRAConfig

Controls the PEFT LoRA adapter applied to the base model.

```python
@dataclass(frozen=True)
class LoRAConfig:
    rank: int = 16              # LoRA rank (r). Higher = more params, more capacity.
    alpha: int = 32             # Scaling factor. Common: 2x rank.
    target_modules: tuple[str, ...] = ("q_proj", "v_proj", "k_proj", "o_proj")
    dropout: float = 0.05       # Dropout on LoRA layers. Range: [0, 1).
    bias: str = "none"          # "none", "all", or "lora_only"
    task_type: str = "CAUSAL_LM"
```

**Constraints:**

- `rank >= 1`
- `alpha >= 1`
- `0 <= dropout < 1`
- `target_modules` must not be empty
- `bias` must be one of `"none"`, `"all"`, `"lora_only"`

**Conversion:** `to_peft_config()` lazily imports `peft.LoraConfig` and returns a PEFT-native config object. The lazy import prevents loading PEFT at config construction time.

### 2.2 SFTConfig

Supervised fine-tuning hyperparameters.

```python
@dataclass(frozen=True)
class SFTConfig:
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.03      # Range: [0, 1)
    max_seq_length: int = 2048
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
    dataset_text_field: str = "text"
```

**Constraints:**

- `learning_rate > 0`, finite
- `0 <= warmup_ratio < 1`
- `bf16` and `fp16` cannot both be True

**Conversion:** `to_trl_config(output_dir)` returns a `trl.SFTConfig`. Uses the modern `SFTConfig` class, not the deprecated `TrainingArguments`.

### 2.3 DPOConfig

Direct Preference Optimization hyperparameters.

```python
@dataclass(frozen=True)
class DPOConfig:
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 5e-5
    warmup_ratio: float = 0.1
    max_length: int = 2048
    max_prompt_length: int = 512
    beta: float = 0.1               # Deviation penalty from reference policy
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
```

**Constraints:**

- `learning_rate > 0`, `beta > 0`, both finite
- `0 <= warmup_ratio < 1`
- `bf16` and `fp16` mutually exclusive

**Key parameter:** `beta` controls how far the model can deviate from the reference policy. Lower beta = more aggressive optimization. Higher beta = more conservative. Default 0.1 is the standard starting point from the DPO paper.

### 2.4 KTOConfig

Kahneman-Tversky Optimization -- works with unpaired binary feedback instead of pairwise preferences.

```python
@dataclass(frozen=True)
class KTOConfig:
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 5e-7      # KTO paper recommends 5e-7
    warmup_ratio: float = 0.1
    beta: float = 0.1
    desirable_weight: float = 1.0    # Weight for True (good) examples
    undesirable_weight: float = 1.0  # Weight for False (bad) examples
    max_length: int = 1024
    max_prompt_length: int = 512
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
```

**Constraints:**

- `learning_rate > 0`, `beta > 0`, `desirable_weight > 0`, `undesirable_weight > 0`, all finite
- `0 <= warmup_ratio < 1`

**Key difference from DPO:** KTO does not require paired preferences. Each example has a prompt, a completion, and a binary label (True = desirable, False = undesirable). This dramatically lowers the data barrier since gathering thumbs-up/down feedback is far easier than curating preference pairs.

### 2.5 ORPOConfig

Odds Ratio Preference Optimization -- combines SFT and preference alignment in a single training pass.

```python
@dataclass(frozen=True)
class ORPOConfig:
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 8e-6      # ORPO paper recommends 8e-6
    warmup_ratio: float = 0.1
    beta: float = 0.1               # Odds ratio weight
    max_length: int = 1024
    max_prompt_length: int = 512
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
```

**Key difference:** ORPO eliminates the `sft_then_dpo` two-stage pipeline by performing SFT and preference alignment simultaneously. One pass, one adapter. Uses paired preference data (prompt/chosen/rejected) like DPO.

### 2.6 GRPOConfig

Group Relative Policy Optimization -- online RL method behind DeepSeek-R1.

```python
@dataclass(frozen=True)
class GRPOConfig:
    num_generations: int = 4         # Completions per prompt (DeepSeek used 16)
    temperature: float = 0.7
    max_completion_length: int = 2048
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 1e-5
    warmup_ratio: float = 0.1
    kl_coef: float = 0.001          # KL divergence penalty
    use_vllm: bool = False           # vLLM for fast generation (CUDA only)
    vllm_gpu_utilization: float = 0.5
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
```

**Constraints:**

- `learning_rate > 0`, `temperature > 0`, `kl_coef >= 0`, all finite
- `num_generations >= 1`
- `0 < vllm_gpu_utilization <= 1.0`
- `0 <= warmup_ratio < 1`

**Key difference:** GRPO generates completions online and scores them with reward functions. No static preference data required -- only prompts. The `num_generations` parameter controls how many completions are generated per prompt; more generations improve the group-relative baseline but cost more compute. DeepSeek-R1 used 16; 4 fits a single GPU.

When `use_vllm=True`, `vllm_gpu_utilization` is passed to TRL's GRPOConfig, which manages the vLLM process internally. This is separate from the standalone `VLLMBackend` class.

### 2.7 RLOOConfig

REINFORCE Leave-One-Out -- same infrastructure as GRPO with a different optimization technique.

```python
@dataclass(frozen=True)
class RLOOConfig:
    num_generations: int = 4
    temperature: float = 0.7
    max_completion_length: int = 2048
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 1e-5
    warmup_ratio: float = 0.1
    kl_coef: float = 0.001
    use_vllm: bool = False
    vllm_gpu_utilization: float = 0.5
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
```

**Same constraints as GRPOConfig.** RLOO generates multiple completions per prompt and uses a leave-one-out baseline for variance reduction. Requires reward functions. Same dataset format (prompt-only).

### 2.8 OnlineDPOConfig

Online DPO -- DPO with online generation. Generates completions online and uses a reward model to score pairs, then applies DPO loss.

```python
@dataclass(frozen=True)
class OnlineDPOConfig:
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 5e-5
    warmup_ratio: float = 0.1
    beta: float = 0.1
    max_length: int = 2048
    max_prompt_length: int = 512
    max_completion_length: int = 512
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
    use_vllm: bool = False
    vllm_gpu_utilization: float = 0.5
```

**Requires generation backend** but does NOT require reward functions (uses a reward model internally for scoring pairs).

### 2.9 AlignmentConfig

Top-level configuration that aggregates all method-specific configs and pipeline parameters.

```python
@dataclass
class AlignmentConfig:
    method: str = "sft_then_dpo"
    base_model_id: str = ""          # REQUIRED (validated non-empty)
    lora: LoRAConfig = field(default_factory=LoRAConfig)
    sft: SFTConfig = field(default_factory=SFTConfig)
    dpo: DPOConfig = field(default_factory=DPOConfig)
    kto: Optional[KTOConfig] = None
    orpo: Optional[ORPOConfig] = None
    grpo: Optional[GRPOConfig] = None
    rloo: Optional[RLOOConfig] = None
    online_dpo: Optional[OnlineDPOConfig] = None
    loss_type: Optional[str] = None  # DPO loss variant: "ipo", "simpo", etc.
    reward_funcs: list[str] = field(default_factory=list)
    use_qlora: bool = False
    experiment_dir: str = "./align-experiments"
    local_files_only: bool = False
    base_model_revision: Optional[str] = None
    onprem: Optional[OnPremConfig] = None
```

**Validation behavior:**

- `method` is validated against `METHOD_REGISTRY` or the special value `"sft_then_dpo"`.
- `base_model_id` must be non-empty.
- If `use_qlora=True`, `bitsandbytes` import is tested immediately. Raises `ImportError` with install instructions if missing.
- Method-specific configs are auto-created with defaults if not provided when the corresponding method is selected. For example, setting `method="kto"` without providing a `kto` config will auto-create `KTOConfig()` with defaults.

**`get_method_config(method_name)`** returns the method-specific config for TRL config generation. For experimental methods without dedicated configs (cpo, bco, xpo, nash_md), falls back to `self.sft` as a base set of training arguments.

**`validate()`** returns a list of warning strings. Empty list = valid. Checks include: missing configs for selected method, online methods without reward functions configured.

### 2.10 AdapterSignature

Describes a LoRA adapter's characteristics. Separate from any ML ModelSignature.

```python
@dataclass(frozen=True)
class AdapterSignature:
    base_model_id: str          # REQUIRED
    adapter_type: str = "lora"  # "lora" or "qlora"
    rank: int = 16
    alpha: int = 32
    target_modules: tuple[str, ...] = ("q_proj", "v_proj")
    task_type: str = "CAUSAL_LM"
    training_method: str = "sft"  # Any METHOD_REGISTRY key or "sft_then_dpo"
```

**Validation:** `training_method` is validated against `METHOD_REGISTRY` via `validate_method_name()` at construction time. `adapter_type` must be `"lora"` or `"qlora"`.

### 2.11 ServingConfig

```python
@dataclass(frozen=True)
class ServingConfig:
    target: str = "ollama"       # "ollama" or "vllm"
    quantization: str = "q4_k_m" # "f16", "q4_k_m", or "q8_0"
    system_prompt: Optional[str] = None
    ollama_host: str = "http://localhost:11434"
    validate_gguf: bool = True   # MANDATORY per R1-02
    validation_timeout: int = 120
```

### 2.12 EvalConfig

```python
@dataclass(frozen=True)
class EvalConfig:
    tasks: tuple[str, ...] = ("arc_easy", "hellaswag", "truthfulqa_mc1")
    limit: int = 100             # Samples per task. Default 100 for interactive use.
    batch_size: str = "auto"
    num_fewshot: Optional[int] = None
    device: Optional[str] = None
    local_files_only: bool = False
    use_adapter: bool = True     # True = eval adapter on base. False = eval base only.
```

**Task presets:**

- `["quick"]` resolves to `["arc_easy", "hellaswag", "truthfulqa_mc1"]` (~5 min on single GPU)
- `["standard"]` resolves to `["arc_easy", "arc_challenge", "hellaswag", "truthfulqa_mc1", "winogrande", "mmlu"]` (~30-60 min on A100)

### 2.13 OnPremConfig

```python
@dataclass
class OnPremConfig:
    offline_mode: bool = False
    model_cache_dir: str = "~/.cache/kailash-align/models"
    ollama_host: str = "http://localhost:11434"
    vllm_endpoint: Optional[str] = None
```

**`__post_init__`** expands `~` in `model_cache_dir` via `Path.expanduser()`.

When `offline_mode=True`, all HuggingFace Hub downloads are disabled. Models must be pre-cached using the `kailash-align-prepare` CLI.

---

## 3. Method Registry

The `MethodRegistry` replaces hard if-elif dispatch with a data-driven registry. Each training method is described by a `MethodConfig` frozen dataclass. The pipeline resolves the trainer class, config class, dataset validator, and metrics extractor at train time via lazy import.

### 3.1 MethodConfig

```python
@dataclass(frozen=True)
class MethodConfig:
    name: str                           # Registry key: "sft", "dpo", "grpo", etc.
    trainer_module: str                 # Python module: "trl"
    trainer_class_name: str             # Class name: "SFTTrainer"
    config_module: str                  # Config module: "trl"
    config_class_name: str              # Config class: "SFTConfig"
    dataset_validator: Callable         # Validates dataset format before training
    dataset_required_columns: frozenset # For error messages
    metrics_extractor: Callable         # Extracts metrics from TrainOutput
    requires_preference_data: bool      # Needs prompt/chosen/rejected dataset
    requires_reward_func: bool          # Needs reward functions (online RL)
    requires_generation_backend: bool   # Needs vLLM or HF generate (online RL)
    supports_loss_type: bool            # Accepts DPO loss_type variants
    category: str                       # "offline", "unpaired", "online", "monolithic"
```

### 3.2 Registered Methods

| Method       | Trainer          | Category   | Preference Data | Reward Func | Generation Backend | Loss Type | Dataset Columns               |
| ------------ | ---------------- | ---------- | --------------- | ----------- | ------------------ | --------- | ----------------------------- |
| `sft`        | SFTTrainer       | offline    | No              | No          | No                 | No        | `{text}`                      |
| `dpo`        | DPOTrainer       | offline    | Yes             | No          | No                 | Yes       | `{prompt, chosen, rejected}`  |
| `kto`        | KTOTrainer       | unpaired   | No              | No          | No                 | No        | `{prompt, completion, label}` |
| `orpo`       | ORPOTrainer      | monolithic | Yes             | No          | No                 | No        | `{prompt, chosen, rejected}`  |
| `grpo`       | GRPOTrainer      | online     | No              | Yes         | Yes                | No        | `{prompt}`                    |
| `rloo`       | RLOOTrainer      | online     | No              | Yes         | Yes                | No        | `{prompt}`                    |
| `online_dpo` | OnlineDPOTrainer | online     | No              | No          | Yes                | No        | `{prompt}`                    |
| `cpo`        | CPOTrainer       | offline    | Yes             | No          | No                 | No        | `{prompt, chosen, rejected}`  |
| `xpo`        | XPOTrainer       | online     | No              | Yes         | Yes                | No        | `{prompt}`                    |
| `nash_md`    | NashMDTrainer    | online     | No              | Yes         | Yes                | No        | `{prompt}`                    |
| `bco`        | BCOTrainer       | unpaired   | No              | No          | No                 | No        | `{prompt, completion, label}` |
| `ppo`        | PPOTrainer       | online     | No              | Yes         | Yes                | No        | `{prompt}`                    |

**Special method:** `sft_then_dpo` is a combo handled directly by the pipeline (not in the registry). It runs SFT first, merges the result, then runs DPO on the merged model.

### 3.3 Dataset Validators

Four validators enforce column presence and non-empty datasets:

- **`_validate_sft_columns`** -- Only checks dataset is non-empty. SFT expects a `text` column (configurable via `dataset_text_field`) but does not enforce column names.
- **`_validate_preference_columns`** -- Requires `{prompt, chosen, rejected}`. Raises `TrainingError` with missing columns listed.
- **`_validate_unpaired_columns`** -- Requires `{prompt, completion, label}`. Same error pattern.
- **`_validate_prompt_only`** -- Requires `{prompt}` column. Used by all online methods.

### 3.4 Metrics Extractors

Three extractors pull metrics from TRL `TrainOutput`:

- **`_extract_standard_metrics`** -- `train_loss`, `train_runtime`, `train_samples_per_second`
- **`_extract_dpo_metrics`** -- Standard + `rewards_chosen`, `rewards_rejected`, `rewards_margin`
- **`_extract_grpo_metrics`** -- Standard + `reward_mean`, `kl_divergence`

### 3.5 Lazy Import

`_lazy_import(module_name, class_name)` is called at train time, not at method registration time. This means importing `kailash_align` never loads any TRL trainer class. If TRL is not installed or the trainer class does not exist in the installed version, the error is raised only when `train()` is called.

### 3.6 Registration API

```python
register_method(MethodConfig(...))   # Add a method to the global registry
get_method("sft")                    # Look up by name, raises AlignmentError if not found
validate_method_name("sft_then_dpo") # Validates name against registry + special combo
```

Users can register custom methods at application startup. The registry is a module-level `dict[str, MethodConfig]`.

---

## 4. AlignmentPipeline

The central orchestrator. Accepts an `AlignmentConfig` and an optional `AdapterRegistry`, then runs training for any registered method.

### 4.1 Constructor

```python
AlignmentPipeline(
    config: AlignmentConfig,
    adapter_registry: Any = None,  # Optional AdapterRegistry for tracking
)
```

### 4.2 train()

```python
async def train(
    dataset: Any,                      # HuggingFace Dataset
    adapter_name: str,                 # Name for the adapter
    preference_dataset: Any = None,    # For preference methods
    reward_funcs: list[str] = None,    # Reward function names from RewardRegistry
) -> AlignmentResult
```

**Dispatch logic:**

1. If `method == "sft_then_dpo"`:
   - Validates `preference_dataset` is provided.
   - Runs SFT on `dataset`, producing an intermediate adapter (`adapter_name-sft`).
   - Merges the SFT adapter into the base model.
   - Runs DPO on `preference_dataset` using the merged model as the new base.
   - Returns the DPO adapter result.

2. For all other methods:
   - Looks up the method in `METHOD_REGISTRY`.
   - Determines which dataset to use based on `requires_preference_data`.
   - Resolves reward functions from `RewardRegistry` if `requires_reward_func` is True.
   - Calls `_run_training()`.

**Error conditions:**

- `TrainingError` if preference methods lack `preference_dataset`.
- `TrainingError` if online methods lack reward functions (neither in `reward_funcs` arg nor `config.reward_funcs`).

### 4.3 \_run_training() (Internal)

The unified training implementation for all methods. Steps:

1. **Validate dataset** via the method's `dataset_validator`.
2. **Create experiment directory** at `{config.experiment_dir}/{adapter_name}/{method_name}/`.
3. **Load base model** with `AutoModelForCausalLM.from_pretrained()`:
   - Respects `local_files_only` and `onprem.offline_mode`.
   - Respects `base_model_revision` for reproducibility.
   - Uses `onprem.model_cache_dir` as `cache_dir` if configured.
   - Sets `trust_remote_code=False` always.
   - If `use_qlora=True`, applies `BitsAndBytesConfig` with NF4 4-bit quantization.
4. **Load tokenizer** with `AutoTokenizer.from_pretrained()`. Sets `pad_token = eos_token` if pad token is not defined.
5. **Apply LoRA** via `peft.get_peft_model()`:
   - If `base_adapter_path` is provided (sft_then_dpo chaining), loads the base adapter with `PeftModel.from_pretrained()`, merges it with `merge_and_unload()`, then applies a fresh LoRA config.
   - Logs trainable vs total parameters and percentage.
6. **Create TRL config** from the method-specific config's `to_trl_config(output_dir)`.
   - If the method supports `loss_type` and the config has one set, applies it to the TRL config.
7. **Create trainer** by lazy-importing the TRL trainer class.
   - `trainer_kwargs` includes: `model`, `args` (TRL config), `train_dataset`, `processing_class` (tokenizer).
   - Offline methods add `peft_config` to trainer kwargs.
   - Online methods with reward functions add `reward_funcs` to trainer kwargs.
8. **Train** with `trainer.train()`. Supports checkpoint resume via `_find_checkpoint()` which finds the latest `checkpoint-*` directory in the experiment dir.
9. **Save adapter** to `{experiment_dir}/adapter/`. Saves both model weights and tokenizer.
10. **Register in AdapterRegistry** (if registry provided):
    - Creates an `AdapterSignature` with base model, adapter type, rank, alpha, target modules, and training method.
    - Calls `registry.register_adapter()` with metrics from the method's `metrics_extractor`.
11. **Return `AlignmentResult`**.

### 4.4 AlignmentResult

```python
@dataclass
class AlignmentResult:
    adapter_name: str         # Human-readable name
    adapter_path: str         # Path to saved LoRA adapter weights
    adapter_version: Any      # AdapterVersion from registry (None if no registry)
    training_metrics: dict    # Metrics dict from TRL trainer
    experiment_dir: str       # Directory with checkpoints and output
    method: str               # Training method used
```

### 4.5 QLoRA Configuration

When `use_qlora=True`, the base model is loaded with `BitsAndBytesConfig`:

- `load_in_4bit=True`
- `bnb_4bit_quant_type="nf4"` (NormalFloat4)
- `bnb_4bit_compute_dtype=torch.bfloat16`
- `bnb_4bit_use_double_quant=True`
- `torch_dtype` is forced to `torch.bfloat16`

This reduces model memory by ~4x compared to float16 loading. Requires the `[rlhf]` extra.

### 4.6 Checkpoint Resume

`_find_checkpoint(experiment_dir)` globs for `checkpoint-*` directories and returns the one with the highest numeric suffix. This enables automatic training resume after interruptions without explicit checkpoint path management.

---

## 5. Training Methods -- When to Use Each

### 5.1 SFT (Supervised Fine-Tuning)

**What it does:** Trains the model to generate specific outputs given specific inputs. Standard next-token prediction on instruction-response pairs.

**When to use:**

- First step in most alignment pipelines.
- You have instruction-response pairs (e.g., ShareGPT format).
- You want domain adaptation (teach the model your vocabulary, style, format).
- Foundation for `sft_then_dpo` combo.

**Dataset format:** Single column (configurable via `dataset_text_field`, default `"text"`) containing the full training text. Each row is one training example.

**Configuration defaults:** 3 epochs, lr=2e-4, batch_size=4, max_seq_length=2048.

### 5.2 DPO (Direct Preference Optimization)

**What it does:** Teaches the model to prefer "chosen" responses over "rejected" responses without training a separate reward model. Uses the reference policy (original model) as an implicit reward.

**When to use:**

- You have high-quality preference pairs (prompt + chosen + rejected).
- After SFT for preference alignment (the `sft_then_dpo` combo).
- Standalone when base model is already instruction-tuned.

**Dataset format:** Columns: `prompt`, `chosen`, `rejected`.

**Key parameter:** `beta` (default 0.1) -- lower values allow more deviation from the reference model (more aggressive optimization), higher values keep the model closer to the reference (more conservative).

**Loss type variants:** DPO supports `loss_type` for variants like `"ipo"` (Identity Preference Optimization) and `"simpo"` (Simple Preference Optimization). Set via `AlignmentConfig.loss_type`.

**Configuration defaults:** 1 epoch, lr=5e-5, beta=0.1, max_length=2048, max_prompt_length=512.

### 5.3 sft_then_dpo (Combo Method)

**What it does:** Two-stage pipeline. Stage 1: SFT on instruction data. Stage 2: DPO on preference data using the SFT adapter as the starting point.

**When to use:**

- Starting from a base model (not instruction-tuned).
- You have both instruction data AND preference data.
- Most common production pipeline.

**How it works internally:**

1. Runs SFT, saves adapter as `{adapter_name}-sft`.
2. Loads the SFT adapter, merges it into the base model via `merge_and_unload()`.
3. Applies a fresh LoRA config to the merged model.
4. Runs DPO on the preference dataset.
5. Returns the final DPO adapter.

**Requires:** Both `dataset` (SFT data) and `preference_dataset` (DPO data).

### 5.4 KTO (Kahneman-Tversky Optimization)

**What it does:** Alignment from unpaired binary feedback. Each example has a prompt, a completion, and a True/False label indicating whether the completion is desirable.

**When to use:**

- You have thumbs-up / thumbs-down feedback (not preference pairs).
- Your preference data is too noisy for reliable pairing.
- You want to lower the data collection barrier dramatically.

**Dataset format:** Columns: `prompt`, `completion`, `label` (boolean or binary).

**Key parameters:**

- `desirable_weight` and `undesirable_weight` control the relative importance of positive vs negative examples.
- Learning rate should be much lower than DPO (paper recommends 5e-7 vs DPO's 5e-5).

**Configuration defaults:** 1 epoch, lr=5e-7, beta=0.1, max_length=1024.

### 5.5 ORPO (Odds Ratio Preference Optimization)

**What it does:** Combines SFT and preference alignment into a single pass using an odds-ratio-based objective. Eliminates the need for a two-stage pipeline.

**When to use:**

- You want to skip `sft_then_dpo` and train in one pass.
- You have paired preference data (prompt/chosen/rejected).
- Faster and simpler pipeline than the two-stage approach.

**Dataset format:** Columns: `prompt`, `chosen`, `rejected` (same as DPO).

**Configuration defaults:** 1 epoch, lr=8e-6, beta=0.1, max_length=1024.

### 5.6 GRPO (Group Relative Policy Optimization)

**What it does:** Online RL method. Generates multiple completions per prompt, scores them with reward functions, and uses group-relative advantages for policy updates. The method behind DeepSeek-R1.

**When to use:**

- You have verifiable reward signals (code correctness, math accuracy, format compliance).
- You want to train reasoning capabilities.
- You have enough compute for online generation (GPU-intensive).

**Dataset format:** Single column: `prompt`. No static responses needed.

**Requires:** Reward functions registered in `RewardRegistry`.

**Key parameters:**

- `num_generations`: Completions per prompt. More = better baseline but more compute. DeepSeek used 16; 4 fits a single GPU.
- `kl_coef`: KL divergence penalty. Prevents the model from drifting too far from the reference. 0.001 is a common starting point.
- `use_vllm`: Uses vLLM for fast generation. CUDA only.

**Configuration defaults:** 1 epoch, lr=1e-5, num_generations=4, temperature=0.7, kl_coef=0.001.

### 5.7 RLOO (REINFORCE Leave-One-Out)

**What it does:** Same setup as GRPO (online generation + reward scoring) but uses a leave-one-out baseline for variance reduction instead of group-relative advantages.

**When to use:**

- Same use cases as GRPO.
- May converge better than GRPO on some tasks due to the LOO baseline.

**Dataset format:** Same as GRPO (`prompt` column only).

**Configuration defaults:** Same as GRPO.

### 5.8 Experimental Methods

The following are registered in `METHOD_REGISTRY` but do not have dedicated config dataclasses. They fall back to `SFTConfig` for base training arguments:

- **CPO** (Contrastive Preference Optimization) -- offline, paired preference data.
- **BCO** (Binary Classifier Optimization) -- unpaired, prompt/completion/label.
- **XPO** (Exploratory Preference Optimization) -- online, reward functions, generation backend.
- **NashMD** (Nash Mirror Descent) -- online, reward functions, generation backend.
- **PPO** (Proximal Policy Optimization) -- online, reward functions, generation backend.

---

## 6. Reward Functions and Registry

### 6.1 RewardFunction Protocol

```python
@runtime_checkable
class RewardFunction(Protocol):
    def __call__(
        self,
        completions: list[str],
        prompts: list[str],
        **kwargs: Any,
    ) -> list[float]: ...
```

Returns one float score per completion. Higher scores = better completions.

### 6.2 Security Constraints

Reward functions are security-critical because they are arbitrary Python callables. The following are explicitly BLOCKED:

- NO pickle serialization of reward functions
- NO `importlib.import_module()` from user-provided strings for rewards
- NO `eval()` or `exec()` on reward function definitions
- Config files reference reward functions by NAME only
- RewardRegistry is in-process only (not distributed)

### 6.3 RewardRegistry

Module-level singleton: `reward_registry = RewardRegistry()`.

```python
# Decorator registration
@reward_registry.register("my_reward")
def my_reward(completions, prompts, **kwargs):
    return [1.0 for _ in completions]

# Programmatic registration
reward_registry.register_function("my_reward", my_func)

# Lookup
func = reward_registry.get("my_reward")  # KeyError if not found

# List
names = reward_registry.list_names()  # Sorted list of registered names
```

### 6.4 Built-in Reward Functions

**`exact_match`** -- 1.0 if `completion.strip() == expected.strip()`, 0.0 otherwise. Requires `expected` kwarg.

**`contains_answer`** -- 1.0 if `expected.strip()` appears anywhere in the completion, 0.0 otherwise. Requires `expected` kwarg.

**`length_penalty`** -- 1.0 for completions within `max_length` chars. Linearly decays to 0.0 for longer completions. `max_length` default: 1024.

### 6.5 Reward Validation

`validate_rewards(rewards, num_completions)` checks:

1. `rewards` is a `list`
2. Length matches `num_completions`
3. All values are numeric (`int` or `float`)
4. All values are finite (no NaN, no Inf)

Raises `RewardValidationError` on any violation.

---

## 7. GPU Memory Estimation

### 7.1 estimate_training_memory()

```python
def estimate_training_memory(
    model_id: str,                          # Used to estimate parameter count
    lora_rank: int = 16,
    lora_target_modules: int = 4,
    batch_size: int = 4,
    seq_length: int = 2048,
    gradient_accumulation_steps: int = 4,
    use_qlora: bool = False,
    gradient_checkpointing: bool = True,
    dtype: str = "bfloat16",
    available_gpu_memory_gb: Optional[float] = None,  # None = auto-detect
    is_online_method: bool = False,
) -> GPUMemoryEstimate
```

**Memory breakdown:**

1. **Model memory** = `num_params * bytes_per_param`. QLoRA uses 0.5 bytes/param (4-bit). bf16/fp16 uses 2 bytes/param. fp32 uses 4 bytes/param.
2. **Adapter memory** = `2 * hidden_dim * rank * target_modules * 2 bytes` (always fp16 for LoRA params).
3. **Optimizer memory** = `lora_params * 2 * 4 bytes` (AdamW stores 2 fp32 states per trainable param).
4. **Gradient memory** = `lora_params * 2 bytes` (fp16 gradients).
5. **Activation memory** = `batch * seq_len * hidden_dim * layer_factor * 2 bytes`. With gradient checkpointing, layer_factor = sqrt(num_layers). Without, layer_factor = num_layers.
6. **Online overhead** = +15% of model memory for KV cache (applied when `is_online_method=True`).
7. **Total** = sum of all \* 1.2 (20% safety margin).

**Parameter estimation from model ID:** Parses model ID string for size indicators (`1b`, `3b`, `7b`, `8b`, `13b`, `14b`, `30b`, `34b`, `70b`). Falls back to 7B if no size indicator is found.

**Hidden dimension estimation:** `sqrt(num_params / 12)` -- rough heuristic.

**Layer count estimation:** `num_params / (hidden_dim^2 * 12)`.

**Batch size recommendation:** If the estimated total exceeds available GPU memory, tries batch_size/2, then 2, then 1, and recommends the largest batch size that fits.

### 7.2 GPUMemoryEstimate

```python
@dataclass(frozen=True)
class GPUMemoryEstimate:
    model_memory_gb: float
    adapter_memory_gb: float
    optimizer_memory_gb: float
    gradient_memory_gb: float
    activation_memory_gb: float
    total_estimate_gb: float
    recommended_batch_size: int
    fits_in_memory: bool
    notes: list[str]           # Warnings and recommendations
```

### 7.3 GPU Detection

**CUDA:** Uses `torch.cuda.get_device_properties()` for total memory and `torch.cuda.mem_get_info()` for free memory.

**Apple Silicon (MPS):** Estimates from system memory via `sysctl -n hw.memsize`. Assumes MPS can use ~75% of system memory.

**No GPU:** Returns `None` for available memory. `fits_in_memory` defaults to `True` (assumes the user knows what they're doing).

### 7.4 get_gpu_info()

Returns `list[GPUInfo]` with device_index, name, total_memory_gb, free_memory_gb for all available GPUs. Returns an empty list if no GPU is found.

---

## 8. Dataset Handling

### 8.1 Format Requirements by Method

| Method Category                                      | Required Columns                | Format                                                   |
| ---------------------------------------------------- | ------------------------------- | -------------------------------------------------------- |
| SFT                                                  | `text` (configurable)           | Each row = one training example (instruction + response) |
| Paired preference (DPO, ORPO, CPO)                   | `prompt`, `chosen`, `rejected`  | Each row = one preference pair                           |
| Unpaired preference (KTO, BCO)                       | `prompt`, `completion`, `label` | Each row = one binary feedback example                   |
| Online RL (GRPO, RLOO, Online DPO, XPO, NashMD, PPO) | `prompt`                        | Each row = one prompt (completions generated online)     |

### 8.2 Validation

Dataset validation happens at the start of `_run_training()` before any model loading. Each method's `dataset_validator` checks:

1. Dataset is non-empty (`len(dataset) > 0`).
2. Required columns exist in `dataset.column_names`.

Validation raises `TrainingError` with the missing columns listed and the expected column set.

### 8.3 Dataset for sft_then_dpo

Requires two datasets:

- `dataset` parameter: SFT data with `text` column.
- `preference_dataset` parameter: DPO data with `prompt`, `chosen`, `rejected` columns.

### 8.4 HuggingFace Dataset Contract

Datasets must be HuggingFace `Dataset` objects (from the `datasets` library). They must support:

- `len(dataset)` for size.
- `dataset.column_names` for column introspection.
- `dataset[i]` for row access.
- `dataset["column_name"]` for column access.
