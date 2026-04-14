# Kailash Align Serving Specification

Parent domain: LLM fine-tuning / alignment (`kailash-align`). Companion file: `alignment-training.md`.

Domain truth document for `kailash-align` v0.3.1, Apache-2.0, Terrene Foundation.

Package: `pip install kailash-align`

This file specifies the **serving and lifecycle side** of kailash-align: adapter registry (versioning, stages, merge status), adapter merging, model serving (GGUF export, Ollama, vLLM config), generation backends (VLLMBackend, HFGenerationBackend), evaluation framework, Kaizen model bridge, on-prem model caching, advisory agents, and serving-side constraints/edge cases. For architecture, configuration, method registry, training pipeline, training methods, reward functions, GPU memory estimation, and dataset handling, see `alignment-training.md`.

---

## 1. Adapter Registry

In-memory registry tracking adapters through their lifecycle: training -> evaluation -> merge -> GGUF export -> deployment.

### 1.1 Design Decisions

- **Composition over inheritance:** `AdapterRegistry` HAS-A optional `ModelRegistry` reference (from kailash-ml). It does NOT inherit from `ModelRegistry`. `AlignAdapter` and `AlignAdapterVersion` are standalone records.
- **In-memory store:** Uses plain dicts. No database dependency. Records are `dict[str, Any]` internally, returned as `AdapterVersion` dataclasses externally.
- **Bounded:** Maximum 10,000 adapters and 1,000 versions per adapter to prevent OOM in long-running processes.

### 1.2 AdapterVersion

```python
@dataclass
class AdapterVersion:
    adapter_id: str
    adapter_name: str
    version: str                   # Monotonically increasing string ("1", "2", ...)
    stage: str                     # "staging" | "shadow" | "production" | "archived"
    adapter_path: str              # Path to LoRA adapter weights
    base_model_id: str
    base_model_revision: Optional[str]
    lora_config: dict              # {r, alpha, target_modules, adapter_type, task_type}
    training_metrics: dict
    merge_status: str              # "separate" | "merged" | "exported"
    merged_model_path: Optional[str]
    gguf_path: Optional[str]
    quantization_config: Optional[dict]
    eval_results: Optional[dict]
    created_at: str                # ISO 8601 UTC timestamp
```

### 1.3 Stage Progression

Stages are monotonic -- only forward transitions are allowed:

```
staging -> shadow -> production -> archived
```

Attempting a backward transition (e.g., production -> staging) raises `AlignmentError`.

### 1.4 Merge Status Lifecycle

```
separate -> merged -> exported
```

- **separate**: LoRA adapter exists independently. Base model + adapter needed for inference.
- **merged**: Adapter merged into base model via `merge_and_unload()`. Standalone HF model.
- **exported**: Merged model converted to GGUF format.

### 1.5 API

```python
# Create / register
await registry.register_adapter(name, adapter_path, signature, training_metrics, ...)
    -> AdapterVersion  # Always creates a new version. Stage = "staging", merge_status = "separate".

# Read
await registry.get_adapter(name, version=None, stage=None)
    -> AdapterVersion  # version=None returns latest. stage filters by stage.

await registry.list_adapters(base_model_id=None, stage=None, tags=None)
    -> list[AdapterVersion]  # Returns latest version of each matching adapter.

# Update
await registry.promote(name, version, stage)
    -> AdapterVersion  # Forward stage transition only.

await registry.update_merge_status(name, version, merge_status, merged_model_path=None)
    -> AdapterVersion

await registry.update_gguf_path(name, version, gguf_path, quantization_config=None)
    -> AdapterVersion  # Also sets merge_status = "exported".

await registry.update_eval_results(name, version, eval_results)
    -> AdapterVersion

# Delete
await registry.delete_adapter(name, version=None)
    # version=None deletes adapter + all versions. version=str deletes that version only.
```

### 1.6 DataFlow Model Fields

`models.py` defines the schema for persisting adapters in DataFlow if desired:

**ALIGN_ADAPTER_FIELDS:**

- `id`, `name`, `model_type`, `base_model_id`, `base_model_revision`, `lora_config_json`, `training_data_ref`, `tags_json`, `onnx_status`, `created_at`

**ALIGN_ADAPTER_VERSION_FIELDS:**

- `id`, `adapter_id`, `version`, `stage`, `adapter_path`, `base_model_id`, `lora_config_json`, `training_metrics_json`, `merge_status`, `merged_model_path`, `gguf_path`, `quantization_config_json`, `eval_results_json`, `created_at`

JSON columns use TEXT storage (same pattern as kailash-ml's `MLModelVersion.metrics_json`).

---

## 2. Adapter Merging

### 2.1 AdapterMerger

Merges LoRA adapters into base models using PEFT's `merge_and_unload()`. After merge, the resulting model is a standard HuggingFace model loadable without PEFT.

**Required for:**

- GGUF export (conversion tools expect a full model, not base + adapter)
- vLLM serving (vLLM loads HF models directly)
- Distribution (merged models are simpler to share)

### 2.2 merge()

```python
async def merge(
    adapter_name: str,
    version: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Path
```

**Steps:**

1. Look up adapter in registry.
2. **Idempotent:** If already merged, returns existing `merged_model_path` without doing anything.
3. **Guard:** If merge_status is `"exported"`, raises `MergeError` (cannot re-merge an exported adapter).
4. Load base model with `AutoModelForCausalLM.from_pretrained()` in fp16 with `device_map="auto"`.
5. Load adapter with `PeftModel.from_pretrained()`.
6. Call `model.merge_and_unload()`.
7. Save merged model + tokenizer to `output_dir` (default: `{adapter_path}/../merged/`).
8. Update registry: `merge_status = "merged"`, `merged_model_path = output_path`.

### 2.3 Convenience Function

```python
await merge_adapter(adapter_name, version=None, output_dir=None, adapter_registry=None)
```

One-shot merge. Creates an `AdapterMerger` internally.

---

## 3. Model Serving

### 3.1 AlignmentServing

Handles the path from trained adapter to deployed model. Two deployment targets: Ollama (for GGUF-based local inference) and vLLM (for GPU-based OpenAI-compatible serving).

### 3.2 deploy() -- Unified Dispatch

```python
async def deploy(adapter_name, version=None, model_name=None, **kwargs)
```

Dispatches to `deploy_ollama()` or `generate_vllm_config()` based on `ServingConfig.target`.

### 3.3 GGUF Export

```python
async def export_gguf(adapter_name, version=None, output_dir=None, quantization=None) -> Path
```

**Requires:** `[serve]` extra (`llama-cpp-python`, `gguf`).

**Steps:**

1. Verify adapter is merged (raises `ServingError` if `merge_status == "separate"`).
2. Check model architecture against supported list:
   - `LlamaForCausalLM`: fully_supported
   - `MistralForCausalLM`: fully_supported
   - `Phi3ForCausalLM`: supported
   - `Qwen2ForCausalLM`: supported
   - Unknown architectures: WARN but proceed.
3. Convert HF model to F16 GGUF via llama-cpp-python's bundled converter or `gguf` CLI.
4. If quantization is not `"f16"`, quantize via `llama_model_quantize()`:
   - `q4_k_m`: 4-bit K-quant medium (best size/quality tradeoff)
   - `q8_0`: 8-bit (good quality/size balance)
5. **Mandatory validation** (R1-02): Load the GGUF file with `llama_cpp.Llama`, run a single-prompt inference ("Hello, "), verify:
   - File loads without crash.
   - Model generates at least one token.
   - Output is not garbage (>50% printable characters).
6. Update registry with `gguf_path` and `quantization_config`.

**Flag injection prevention:** All `subprocess.run()` calls use `"--"` to separate flags from model paths, preventing crafted model paths from being interpreted as command-line flags.

### 3.4 Ollama Deployment

```python
async def deploy_ollama(adapter_name, version=None, model_name=None, gguf_path=None)
```

**Normal path:** Calls `export_gguf()` -> writes Modelfile -> `ollama create` -> `ollama show` verify.

**BYOG (Bring Your Own GGUF) path:** If `gguf_path` is provided, skips GGUF conversion entirely. Useful for pre-converted or third-party GGUF files.

**Modelfile format:**

```
FROM /path/to/model.gguf
SYSTEM """optional system prompt"""
```

**Model name validation:** Must match `^[a-zA-Z0-9_:.-]+$`. Prevents shell injection via model names passed to `subprocess.run()`.

**Ollama availability check:** Runs `ollama list` with a 10-second timeout. Raises `OllamaNotAvailableError` if CLI is not found, returns error, or times out.

### 3.5 vLLM Config Generation

```python
async def generate_vllm_config(adapter_name, version=None, output_path=None)
```

**Does NOT start vLLM.** Produces:

1. A `vllm-config.json` file with model path, dtype, tensor-parallel-size, max-model-len, gpu-memory-utilization, host, port.
2. A `launch_vllm.sh` script that invokes `vllm.entrypoints.openai.api_server`.

**Adapter name sanitization:** `re.sub(r"[^\w.:-]", "_", adapter_name)` for use in shell script comments.

**NOTE (R2-03):** vLLM requires CUDA. Not recommended for Apple Silicon.

---

## 4. Generation Backends

Generation backends provide batch text generation for online RL methods (GRPO, RLOO, Online DPO). Two implementations exist behind the `GenerationBackend` ABC.

### 4.1 GenerationBackend (ABC)

```python
class GenerationBackend(abc.ABC):
    @abc.abstractmethod
    def batch_generate(
        self,
        prompts: list[str],
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.95,
        num_return_sequences: int = 1,
    ) -> list[list[str]]:
        """Outer list = per prompt, inner list = completions per prompt."""

    def shutdown(self) -> None: ...
```

### 4.2 VLLMBackend

**Requires:** `[online]` extra (`vllm>=0.6`). CUDA only.

```python
VLLMBackend(
    model_id: str,
    config: Optional[VLLMConfig] = None,
)
```

**VLLMConfig:**

```python
@dataclass(frozen=True)
class VLLMConfig:
    tensor_parallel_size: int = 1
    gpu_memory_utilization: float = 0.9   # (0, 1]
    max_model_len: Optional[int] = None
    dtype: str = "auto"
    seed: int = 42
```

**Lazy loading:** The vLLM `LLM` instance is created on first `batch_generate()` call, not at construction time. `trust_remote_code=False` always.

**Shutdown:** `del self._llm` to release GPU memory.

### 4.3 HFGenerationBackend

Fallback for non-CUDA environments (Apple Silicon, CPU).

```python
HFGenerationBackend(
    model_id: str,
    device: Optional[str] = None,  # None = auto-detect (cuda > mps > cpu)
)
```

**Auto-detection priority:** CUDA > MPS > CPU.

**Behavior differences from VLLMBackend:**

- Processes prompts one at a time (no batched generation).
- Uses `torch.no_grad()` context.
- Clamps temperature to `max(temperature, 1e-7)` to avoid division by zero.
- Uses `do_sample=temperature > 0` to disable sampling when temperature is 0.
- Truncates input to 2048 tokens.

**Shutdown:** Deletes both model and tokenizer.

---

## 5. Evaluation Framework

### 5.1 AlignmentEvaluator

Two evaluation paths: standard benchmarks via lm-eval-harness, and custom evaluation via transformers pipeline.

```python
AlignmentEvaluator(
    adapter_registry: Any = None,
    onprem_config: Any = None,
)
```

### 5.2 Standard Evaluation (lm-eval)

```python
async def evaluate(adapter_name, version=None, config=None) -> EvalResult
```

**Requires:** `[eval]` extra (`lm-eval>=0.4`). Raises `ImportError` with install instructions if missing.

**Steps:**

1. Resolve task presets ("quick" or "standard") to actual task lists.
2. Look up adapter in registry to get model path.
3. Determine model args: if adapter is separate and `use_adapter=True`, pass `peft` path. If merged, use `merged_model_path` as the pretrained model.
4. Call `lm_eval.simple_evaluate()` with model="hf", tasks, limit, batch_size, num_fewshot, device.
5. Parse results into `TaskResult` objects (one per task).
6. Update AdapterRegistry with eval results.

### 5.3 Custom Evaluation

```python
async def evaluate_custom(adapter_name, dataset, scoring_fn, version=None, batch_size=8) -> EvalResult
```

Does NOT require lm-eval. Uses `transformers.pipeline("text-generation")`.

**Auto-detects input column:** Checks for `text`, `input`, `prompt`, `question` in dataset column names (in that order). Falls back to first column.

**Auto-detects reference column:** Checks for `label`, `answer`, `reference`, `target`.

**Scoring function contract:** `scoring_fn(predictions: list[str], references: list[str] | None) -> dict[str, float]`.

### 5.4 Comparison

```python
async def compare(adapter_a, adapter_b, version_a=None, version_b=None, config=None) -> dict
```

Runs `evaluate()` on both adapters with the same config, then produces a per-task comparison with deltas and an overall average delta.

### 5.5 EvalResult

```python
@dataclass
class EvalResult:
    adapter_name: str
    adapter_version: Optional[str]
    task_results: list[TaskResult]
    eval_config: dict
    total_duration_seconds: float
```

**`summary` property:** Returns `dict[str, float]` mapping task_name to the first metric containing "acc" in its key. Quick way to get accuracy per task.

### 5.6 TaskResult

```python
@dataclass
class TaskResult:
    task_name: str
    metrics: dict[str, float]
    num_samples: int
    task_version: Optional[str] = None
```

Both `EvalResult` and `TaskResult` support `to_dict()` and `from_dict()` for serialization.

---

## 6. Kaizen Model Bridge

### 6.1 Purpose

`KaizenModelBridge` is a factory that creates Kaizen `Delegate` instances configured to use fine-tuned local models deployed via Ollama or vLLM. It uses only public Delegate APIs -- no modifications to Delegate or adapter classes needed.

### 6.2 BridgeConfig

```python
@dataclass(frozen=True)
class BridgeConfig:
    ollama_host: str = "http://localhost:11434"
    vllm_endpoint: Optional[str] = None
    default_strategy: Optional[str] = None  # "ollama" or "vllm". None = auto-detect.
```

### 6.3 create_delegate()

```python
async def create_delegate(
    adapter_name: str,
    version: Optional[str] = None,
    strategy: Optional[str] = None,       # "ollama" or "vllm". None = auto-detect.
    delegate_kwargs: Optional[dict] = None,  # Additional Delegate constructor kwargs
) -> Delegate
```

Returns a configured Kaizen `Delegate` instance. `delegate_kwargs` allows passing `tools`, `system_prompt`, `max_turns`, `max_tokens`, etc.

### 6.4 Strategy Resolution

`resolve_strategy(adapter_version)` auto-detects the serving strategy:

1. If `config.default_strategy` is set, use it.
2. If adapter has a GGUF path and Ollama is available, use `"ollama"`.
3. If `config.vllm_endpoint` is set and reachable, use `"vllm"`.
4. Raise `BridgeNotReadyError`.

**Ollama is recommended for Apple Silicon.** vLLM is CUDA-only in practice.

### 6.5 Delegate Configuration

**Ollama strategy:**

```python
{
    "model": adapter_name,
    "adapter": "ollama",
    "adapter_kwargs": {"host": ollama_host},
}
```

**vLLM strategy:**

```python
{
    "model": adapter_name,
    "adapter": "openai",
    "adapter_kwargs": {"base_url": vllm_endpoint, "api_key": "not-needed"},
}
```

### 6.6 Budget Tracking Constraint (R2-04)

Delegate's `budget_usd` tracking uses cloud API pricing. Local models (Ollama/vLLM) have $0/token cost. If `budget_usd` is set on a governed Delegate using a local model, the budget is never consumed. Use `max_turns` or `max_tokens` for execution bounds on local models instead.

### 6.7 discover_deployed_models()

Queries Ollama's `/api/tags` endpoint to list locally available models. Returns a list of dicts with `model_name`, `size`, `modified_at`, `source`.

---

## 7. On-Premises Model Caching

### 7.1 OnPremModelCache

Wraps HuggingFace Hub's `snapshot_download()` and `scan_cache_dir()` for air-gapped model management.

**Usage pattern:**

```python
# Online: pre-cache models
cache = OnPremModelCache(cache_dir="./models")
cache.download("meta-llama/Llama-3.1-8B")

# Offline: configure pipeline to use cache
config = OnPremConfig(offline_mode=True, model_cache_dir="./models")
pipeline = AlignmentPipeline(AlignmentConfig(onprem=config, ...))
```

### 7.2 API

```python
cache.download(model_id, revision=None, allow_patterns=None) -> Path
    # snapshot_download() with resume support and SHA256 verification

cache.list() -> list[CachedModel]
    # Scans cache directory. Returns model_id, cache_path, size_bytes, revision, is_complete.

cache.verify(model_id) -> bool
    # Checks: files exist, config loads, tokenizer loads. Returns True/False.

cache.cache_path(model_id) -> Path
    # Returns path to cached model. Raises CacheNotFoundError if not cached.
```

### 7.3 OnPremSetupGuide

Generates structured deployment checklists for air-gapped environments.

```python
checklist = OnPremSetupGuide.generate_checklist(
    models=["meta-llama/Llama-3.1-8B", "mistralai/Mistral-7B-v0.1"],
    cache_dir="~/.cache/kailash-align/models",
)
```

Returns a `SetupChecklist` with structured `ChecklistItem` objects covering download, verify, configure, and deploy phases. Each item has `step`, `category`, `description`, `command`, and optional `size_estimate_gb`.

**Renderable as:** `to_dict()` (for API responses) or `to_markdown()` (for human consumption).

**Approximate model sizes** (built-in estimates):

- Llama-2-7b: 13.5 GB
- Meta-Llama-3-8B: 16.0 GB
- Mistral-7B: 14.5 GB
- phi-2: 5.5 GB
- TinyLlama-1.1B: 2.2 GB
- Unknown models: default 10.0 GB

### 7.4 CLI: kailash-align-prepare

Entry point: `kailash-align-prepare` (installed via `[project.scripts]`).

```bash
kailash-align-prepare download META_LLAMA_ID [--revision REV]
kailash-align-prepare list
kailash-align-prepare verify META_LLAMA_ID
```

Uses `click` for CLI parsing. `--cache-dir` option (default `~/.cache/kailash-align/models`) applies to all commands.

---

## 8. Kaizen Advisory Agents

Four LLM-first agents for the fine-tuning lifecycle. All follow the agent reasoning architecture: the LLM does all reasoning via Kaizen Signatures; tools are dumb data endpoints.

**Requires:** `pip install kailash-align[agents]` (installs `kailash-kaizen`).

### 8.1 AlignmentStrategistAgent

**Purpose:** Recommend an alignment strategy given model info, dataset summary, and constraints.

**Signature inputs:** `base_model_info`, `dataset_summary`, `constraints`, `available_methods`

**Signature outputs:** `method_recommendation`, `base_model_assessment`, `data_requirements`, `risks`, `confidence` (0-1)

```python
strategist = AlignmentStrategistAgent(model="...")
result = await strategist.recommend(
    base_model_info="Meta-Llama-3-8B, 8B params, llama architecture",
    dataset_summary="50k rows, prompt/chosen/rejected columns",
)
```

### 8.2 DataCurationAgent

**Purpose:** Evaluate dataset quality and recommend curation strategies.

**Signature inputs:** `dataset_stats`, `preference_quality`, `training_method`

**Signature outputs:** `curation_strategy`, `quality_assessment`, `gaps` (list), `augmentation_suggestions`, `confidence`

### 8.3 TrainingConfigAgent

**Purpose:** Select hyperparameters, LoRA configuration, and hardware requirements.

**Signature inputs:** `training_method`, `model_info`, `gpu_memory`, `dataset_size`, `memory_estimate`

**Signature outputs:** `hyperparameters`, `lora_config`, `hardware_recommendation`, `warnings` (list), `confidence`

### 8.4 EvalInterpreterAgent

**Purpose:** Interpret evaluation results and recommend next steps.

**Signature inputs:** `eval_results`, `training_config`, `baseline`

**Signature outputs:** `interpretation`, `quality_verdict` ("deploy", "iterate", or "retrain"), `next_steps` (list), `risks`, `confidence`

### 8.5 alignment_workflow() Orchestrator

Convenience function composing all four agents in pipeline order:

```
Strategist -> DataCuration -> TrainingConfig -> [optional] EvalInterpreter
```

```python
result = await alignment_workflow(
    base_model_info="...",
    dataset_summary="...",
    gpu_memory="...",
    dataset_size="...",
    eval_results="...",  # Optional: triggers EvalInterpreter
    model="...",         # LLM override for all agents
)
# Returns: {"strategy": ..., "curation": ..., "config": ..., "interpretation": ...}
```

### 8.6 Agent Tools

All tools in `agents/tools.py` are dumb data endpoints with zero decision logic:

| Tool                        | Source                              | Description                                           |
| --------------------------- | ----------------------------------- | ----------------------------------------------------- |
| `get_base_model_info`       | Static lookup                       | Model metadata (params, architecture, context length) |
| `list_training_methods`     | `METHOD_REGISTRY` (real)            | Available methods with metadata                       |
| `estimate_training_cost`    | Heuristic formula                   | Rough cost estimate from model size and dataset       |
| `get_dataset_stats`         | Real dataset object                 | Row count, columns, size                              |
| `check_preference_quality`  | Real dataset object                 | Preference pair stats (length ratio, diversity)       |
| `get_gpu_memory`            | `gpu_memory.get_gpu_info()` (real)  | GPU info from hardware                                |
| `estimate_lora_memory`      | `estimate_training_memory()` (real) | Memory estimate from real engine                      |
| `list_quantization_options` | Static                              | Quantization formats with descriptions                |

---

## 9. Constraints and Edge Cases

### 9.1 trust_remote_code

Set to `False` everywhere: `AutoModelForCausalLM.from_pretrained()`, `AutoTokenizer.from_pretrained()`, `AutoConfig.from_pretrained()`, and vLLM `LLM()`. Models requiring `trust_remote_code=True` are not supported.

### 9.2 Pad Token Handling

If the tokenizer's `pad_token` is `None`, it is set to `eos_token` during training. This is the standard convention for decoder-only models that lack an explicit pad token (e.g., LLaMA).

### 9.3 Offline Mode

Two independent flags control offline behavior:

- `AlignmentConfig.local_files_only`: Direct flag on the pipeline config.
- `OnPremConfig.offline_mode`: Nested in the onprem config.

If EITHER is `True`, `local_files_only=True` is passed to all `from_pretrained()` calls. No HuggingFace Hub requests escape.

### 9.4 Model Revision Pinning

`AlignmentConfig.base_model_revision` can be set to a specific commit hash for reproducibility. When set, it is passed as the `revision` kwarg to `from_pretrained()`.

### 9.5 Concurrent Adapter Versions

Multiple versions of the same adapter can coexist at different stages. The registry tracks them independently. `get_adapter(name)` with no version returns the latest version overall. `get_adapter(name, stage="production")` returns the latest version in the production stage.

### 9.6 Idempotent Merge

Calling `merge()` on an already-merged adapter returns the existing `merged_model_path` without performing any merge operation. This makes it safe to call merge defensively before GGUF export.

### 9.7 GGUF Architecture Limitations

GGUF conversion is tested against four architectures: LlamaForCausalLM, MistralForCausalLM, Phi3ForCausalLM, Qwen2ForCausalLM. Unknown architectures produce a WARN but proceed -- the GGUF validation step catches actual conversion failures.

### 9.8 Apple Silicon Constraints

- vLLM does not work on Apple Silicon (CUDA required).
- `HFGenerationBackend` auto-detects MPS and works on Apple Silicon.
- Ollama is the recommended deployment target for Apple Silicon.
- GPU memory estimation uses `sysctl` to read system memory and estimates MPS can use ~75%.

### 9.9 BitsAndBytes Dependency

QLoRA (`use_qlora=True`) requires `bitsandbytes`, which has limited platform support. The dependency is checked at `AlignmentConfig.__post_init__` time with a clear `ImportError` message pointing to `pip install kailash-align[rlhf]`.

### 9.10 Adapter Registry Bounds

- Maximum 10,000 adapters per registry instance.
- Maximum 1,000 versions per adapter.
- Exceeding either bound raises `AlignmentError` with a message to delete old entries.
- These bounds prevent OOM in long-running processes that continuously register adapters.
