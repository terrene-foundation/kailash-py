# kailash-align Architecture

## 1. Package Structure

### 1.1 Directory Layout

```
packages/kailash-align/
  src/kailash_align/
    __init__.py                    # Lazy imports: AlignmentPipeline, AdapterRegistry, etc.
    adapter_registry.py            # AdapterRegistry (extends ModelRegistry)
    pipeline.py                    # AlignmentPipeline (SFT + DPO)
    evaluator.py                   # AlignmentEvaluator (lm-eval-harness)
    serving.py                     # AlignmentServing (GGUF, Ollama, vLLM)
    bridge.py                      # KaizenModelBridge
    onprem.py                      # OnPremConfig, OnPremModelCache
    cli.py                         # kailash-align-prepare CLI
    agents/
      __init__.py
      alignment_strategist.py
      data_curation.py
      training_config.py
      eval_interpreter.py
      tools.py                     # All agent tools
  tests/
    test_adapter_registry.py
    test_pipeline.py
    test_evaluator.py
    test_serving.py
    test_bridge.py
    test_onprem.py
  pyproject.toml
  README.md
```

### 1.2 pyproject.toml

```toml
[project]
name = "kailash-align"
version = "1.0.0"
description = "LLM fine-tuning and alignment for the Kailash ecosystem"
requires-python = ">=3.10"
license = {text = "Apache-2.0"}
dependencies = [
    "kailash>=1.0",
    "kailash-ml>=1.0",
    "kailash-kaizen>=1.0",
    "torch>=2.2",
    "transformers>=4.40",
    "trl>=0.8",
    "peft>=0.10",
    "accelerate>=0.28",
    "datasets>=2.18",
    "lm-eval>=0.4",
]

[project.optional-dependencies]
rlhf = ["bitsandbytes>=0.43"]
serve = []  # No Python deps; Ollama/vLLM are external binaries
full = ["kailash-align[rlhf,serve]"]

[project.scripts]
kailash-align-prepare = "kailash_align.cli:cli"
```

### 1.3 Dependency Chain

```
kailash (core)
    +-- kailash-dataflow  (ModelRegistry metadata storage)
    +-- kailash-nexus     (optional, for API exposure)
    +-- kailash-kaizen    (KaizenModelBridge, Delegate)
    +-- kailash-ml        (ModelRegistry, for AdapterRegistry to extend)
        +-- kailash-ml-protocols

kailash-align
    +-- kailash, kailash-ml, kailash-kaizen
    +-- torch, transformers, trl, peft, accelerate, datasets, lm-eval
    +-- [rlhf]: bitsandbytes (4-bit/8-bit quantization for QLoRA)
```

**Install size**: ~2.5GB minimum (PyTorch + transformers + model weights). This is unavoidable for LLM work.

---

## 2. AdapterRegistry (WS-A1)

**Purpose**: Extends kailash-ml's `ModelRegistry` for LoRA/QLoRA adapters. Adapters differ from sklearn models:
- Small (50-500MB) but always reference a large base model
- Two states: "separate" (adapter weights only) or "merged" (base+adapter)
- Can be quantized (4-bit QLoRA via bitsandbytes)
- Can be exported to GGUF for Ollama/llama.cpp serving

```python
class AdapterRegistry(ModelRegistry):
    """ModelRegistry extension for LoRA/QLoRA adapters.
    onnx_status = "not_applicable" for all adapters.
    """

    async def register_adapter(
        self, name: str, adapter_path: str, base_model_id: str,
        lora_config: dict, metrics: dict,
        merge_state: str = "separate",
        quantization_config: dict | None = None,
    ) -> AdapterVersion: ...

    async def list_adapters(self, base_model_id: str | None = None) -> list[AdapterVersion]: ...
    async def get_adapter(self, name: str, version: str | None = None) -> AdapterVersion: ...

    async def merge_adapter(self, name: str, version: str) -> AdapterVersion:
        """Merge LoRA weights into base model. Creates merged artifact.
        Uses peft.PeftModel.merge_and_unload()."""
```

**AdapterVersion dataclass**:
```python
@dataclass
class AdapterVersion:
    adapter_path: str
    base_model_id: str
    lora_config: dict        # {"r": 16, "lora_alpha": 32, "target_modules": ["q_proj", "v_proj"], ...}
    merge_state: str         # "separate" | "merged"
    quantization_config: dict | None  # QLoRA config if applicable
    gguf_path: str | None    # Set by AlignmentServing after GGUF export
    registered_at: datetime
```

**DataFlow models**:
- `AlignAdapter` (extends MLModel): adapter-specific fields
- `AlignAdapterVersion` (extends MLModelVersion): lora_config_json, base_model_id, merge_state, gguf_path, quantization_config_json

**LoRA config example**:
```python
{
    "r": 16,                          # LoRA rank
    "lora_alpha": 32,                 # Scaling factor
    "target_modules": ["q_proj", "v_proj"],
    "lora_dropout": 0.1,
    "bias": "none",
    "task_type": "CAUSAL_LM",
}
```

---

## 3. AlignmentPipeline (WS-A2)

**Purpose**: Orchestrate SFT + DPO training sequence with LoRA, checkpoint management, and memory optimization.

```python
class AlignmentPipeline:
    def __init__(self, registry: AdapterRegistry,
                 onprem_config: OnPremConfig | None = None): ...

    async def train(
        self, base_model_id: str, dataset,
        adapter_config: AlignmentConfig,
        experiment_name: str,
    ) -> AlignmentResult: ...
```

**AlignmentConfig dataclass**:
```python
@dataclass
class AlignmentConfig:
    method: str                        # "sft", "dpo", "sft_then_dpo"
    lora_config: dict                  # LoRA hyperparameters
    training_args: dict                # Passed to TRL Trainer
    use_qlora: bool = False            # 4-bit quantization (requires [rlhf] extra)
    gradient_checkpointing: bool = True
    mixed_precision: str = "bf16"      # "bf16" (A100/H100), "fp16" (V100/T4), "no"
    local_model_cache_dir: str | None = None  # Air-gapped model loading
```

**Training flow for `method="sft_then_dpo"`**:
1. Load base model (`AutoModelForCausalLM.from_pretrained()`; `local_files_only=True` if air-gapped)
2. Apply LoRA with `peft.LoraConfig`; if `use_qlora=True`, load in 4-bit via bitsandbytes
3. Run `trl.SFTTrainer` on instruction dataset
4. Save SFT checkpoint, register in AdapterRegistry
5. Run `trl.DPOTrainer` on preference dataset (prompt, chosen, rejected)
6. Save DPO checkpoint, register in AdapterRegistry
7. Return `AlignmentResult`

**AlignmentResult dataclass**:
```python
@dataclass
class AlignmentResult:
    adapter_version: AdapterVersion
    training_metrics: dict
    experiment_id: str
    checkpoint_path: str
    base_model_id: str
    method: str
```

**Air-gapped model loading**:
```python
async def _load_base_model(self, base_model_id, config):
    if self._onprem and self._onprem.offline_mode:
        model_path = OnPremModelCache.cache_path(base_model_id, self._onprem.model_cache_dir)
        load_id = str(model_path)
        local_files_only = True
    else:
        load_id = base_model_id
        local_files_only = False

    load_kwargs = {"local_files_only": local_files_only, "torch_dtype": torch.bfloat16}

    if config.use_qlora:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
        )
        load_kwargs["quantization_config"] = bnb_config

    model = AutoModelForCausalLM.from_pretrained(load_id, **load_kwargs)
    tokenizer = AutoTokenizer.from_pretrained(load_id, local_files_only=local_files_only)
    return model, tokenizer
```

**SFT via TRL**:
```python
async def _run_sft(self, model, tokenizer, dataset, config, checkpoint_dir):
    from trl import SFTTrainer, SFTConfig
    sft_args = SFTConfig(
        output_dir=str(checkpoint_dir / "sft"),
        gradient_checkpointing=config.gradient_checkpointing,
        bf16=config.mixed_precision == "bf16",
        fp16=config.mixed_precision == "fp16",
        **config.training_args.get("sft", {}),
    )
    trainer = SFTTrainer(model=model, tokenizer=tokenizer,
                         train_dataset=dataset["train"], args=sft_args)
    trainer.train()
    trainer.save_model(str(checkpoint_dir / "sft_final"))
    return trainer.state.log_history[-1]
```

**DPO via TRL** (preference data: prompt, chosen, rejected):
```python
async def _run_dpo(self, model, tokenizer, preference_dataset, config, checkpoint_dir):
    from trl import DPOTrainer, DPOConfig
    dpo_args = DPOConfig(
        output_dir=str(checkpoint_dir / "dpo"),
        beta=config.training_args.get("dpo", {}).get("beta", 0.1),
        bf16=config.mixed_precision == "bf16",
        **{k: v for k, v in config.training_args.get("dpo", {}).items() if k != "beta"},
    )
    trainer = DPOTrainer(model=model, ref_model=None, tokenizer=tokenizer,
                         train_dataset=preference_dataset["train"], args=dpo_args)
    trainer.train()
    trainer.save_model(str(checkpoint_dir / "dpo_final"))
    return trainer.state.log_history[-1]
```

**Multi-GPU**: `accelerate` handles distributed coordination transparently. Users launch with `accelerate launch`.

**Checkpoint management**: Saved to `{experiment_dir}/{experiment_name}/checkpoints/`. On failure, latest checkpoint preserved. `resume_from_checkpoint=True` resumes.

**DataFlow tracking**: `AlignExperiment` model stores experiment_id, base_model_id, method, lora_config_json, training_args_json, status, started_at, completed_at.

---

## 4. AlignmentEvaluator (WS-A3)

**Purpose**: Run standardized benchmarks against fine-tuned models. Wraps `lm-eval-harness`.

```python
class AlignmentEvaluator:
    def __init__(self, registry: AdapterRegistry): ...

    async def evaluate(self, adapter_version: AdapterVersion,
                       tasks: list[str], eval_config: EvalConfig | None = None) -> EvalResult: ...

    async def evaluate_custom(self, adapter_version: AdapterVersion,
                               custom_dataset, scoring_fn) -> EvalResult: ...

    async def compare(self, version_a: AdapterVersion,
                      version_b: AdapterVersion, tasks: list[str]) -> ComparisonResult: ...
```

**EvalConfig**:
```python
@dataclass
class EvalConfig:
    batch_size: int = 8
    limit: int | None = None          # Max samples per task
    num_fewshot: int = 0
    local_model_cache_dir: str | None = None
    device: str = "auto"              # "auto", "cpu", "cuda"
```

**Standard benchmarks** (via lm-eval-harness):
- `mmlu` -- 57-task academic knowledge
- `hellaswag` -- commonsense NLI
- `arc_easy`, `arc_challenge` -- science QA
- `truthfulqa_mc1`, `truthfulqa_mc2` -- factual accuracy
- `winogrande` -- commonsense reasoning

**Custom evaluation**: User provides a `datasets.Dataset` with "input" and "reference_output" columns + a `scoring_fn(generated, reference) -> float`. Model generates responses, scoring_fn applied per sample.

**Model loading**: Handles both merged and separate adapters. Separate: loads base + `PeftModel.from_pretrained()`. Merged: loads directly.

**EvalResult**:
```python
@dataclass
class EvalResult:
    adapter_name: str
    adapter_version: str
    base_model_id: str
    task_results: dict[str, TaskResult]  # task_name -> TaskResult
    aggregate_score: float
    evaluated_at: datetime
    eval_config: EvalConfig
```

**DataFlow**: `AlignEvalResult` model stores results alongside adapter version.

---

## 5. AlignmentServing (WS-A4)

**Purpose**: Close the gap from "fine-tuned model" to "running inference service."

```python
class AlignmentServing:
    def __init__(self, registry: AdapterRegistry): ...

    async def deploy(self, adapter_version: AdapterVersion,
                     target: str, **kwargs) -> dict:
        """Unified dispatch: 'ollama', 'gguf', or 'vllm'."""

    async def export_gguf(self, adapter_version: AdapterVersion,
                          output_dir: Path, quantization: str = "q4_k_m") -> Path: ...

    async def deploy_ollama(self, adapter_version: AdapterVersion,
                             model_name: str, ollama_host: str = "http://localhost:11434") -> dict: ...

    def generate_vllm_config(self, adapter_version: AdapterVersion,
                              output_path: Path) -> dict: ...
```

**Three deployment targets**:

### GGUF Export
1. Merge adapter if `merge_state == "separate"` (via `peft.PeftModel.merge_and_unload()`)
2. Save merged model in HuggingFace format
3. Call `llama.cpp`'s `convert_hf_to_gguf.py` via subprocess
4. Quantize with `llama-quantize` if quantization != "f16"
5. Update AdapterRegistry: set `gguf_path`

**Quantization options**: "f16" (no quant, format conversion only), "q4_k_m" (4-bit, recommended), "q8_0" (8-bit)

### Ollama Deployment
1. `export_gguf()` to produce GGUF file
2. Write `Modelfile` with `FROM {gguf_path}` and optional system prompt
3. Run `subprocess.run(["ollama", "create", model_name, "-f", modelfile_path])`
4. Verify with `ollama show {model_name}`

### vLLM Config Generation
Writes `launch_vllm.sh` shell script and JSON config. Does NOT start vLLM (user responsibility).

```python
def _generate_vllm_config(self, adapter_version, merged_model_path):
    return {
        "model": str(merged_model_path),
        "host": "0.0.0.0", "port": 8000,
        "tensor-parallel-size": 1,
        "max-model-len": 4096,
        "dtype": "bfloat16",
        "served-model-name": adapter_version.name,
    }
```

**No Python SDK dependencies**: AlignmentServing uses `subprocess` for Ollama CLI. No `ollama` or `vllm` Python package imports. Raises `ServingError` if binaries not found.

---

## 6. KaizenModelBridge (WS-A5)

**Purpose**: Connect fine-tuned model to Kaizen Delegate. Closes the lifecycle gap.

```python
class KaizenModelBridge:
    def __init__(self, registry: AdapterRegistry,
                 ollama_host: str = "http://localhost:11434",
                 vllm_endpoint: str | None = None): ...

    async def get_delegate_config(self, adapter_name: str,
                                   version: str | None = None,
                                   strategy: str | None = None) -> dict: ...

    async def create_delegate(self, adapter_name: str,
                               version: str | None = None,
                               **delegate_kwargs) -> Delegate: ...

    async def discover_deployed_models(self) -> list[dict]: ...
```

**Model loading strategies**:

| Strategy | Config Output | How Delegate Connects |
|----------|---------------|----------------------|
| `"ollama"` | `{"model": "ollama/{name}", "base_url": "{host}/api"}` | Ollama HTTP API |
| `"vllm"` | `{"model": "openai/{name}", "base_url": "{endpoint}"}` | vLLM OpenAI-compatible API |
| `"local_hf"` | `{"model": "local_hf:{path}", "base_model_id": "..."}` | Direct transformers.pipeline (dev only, slow) |

**Auto-detection**: `resolve_strategy()` checks: Ollama registered? -> "ollama". vllm_endpoint configured? -> "vllm". Else -> "local_hf".

**create_delegate factory**:
```python
async def create_delegate(self, adapter_name, version=None, **delegate_kwargs):
    from kailash_kaizen import Delegate
    config = await self.get_delegate_config(adapter_name, version)
    return Delegate(**config, **delegate_kwargs)
```

---

## 7. On-Prem Workflow (WS-A6)

**Purpose**: Make kailash-align operational in air-gapped environments.

### OnPremConfig
```python
@dataclass
class OnPremConfig:
    model_cache_dir: str
    offline_mode: bool
    ollama_host: str = "http://localhost:11434"
    vllm_endpoint: str | None = None
```

### OnPremModelCache
```python
class OnPremModelCache:
    @staticmethod
    def download(model_id, cache_dir) -> Path:
        """Download model to local cache. Requires internet. Run BEFORE air-gap."""

    @staticmethod
    def list(cache_dir) -> list[dict]:
        """List cached models with sizes and timestamps."""

    @staticmethod
    def verify(model_id, cache_dir) -> bool:
        """Verify model files are complete."""

    @staticmethod
    def cache_path(model_id, cache_dir) -> Path:
        """Returns local path; raises CacheNotFoundError if missing."""
```

### kailash-align-prepare CLI
```
kailash-align-prepare download --model meta-llama/Llama-3.2-8B --cache-dir /data/models
kailash-align-prepare list --cache-dir /data/models
kailash-align-prepare verify --model meta-llama/Llama-3.2-8B --cache-dir /data/models
```

### Offline Mode Propagation
When `onprem_config.offline_mode = True`:
- All `from_pretrained()` calls use `local_files_only=True`
- All `snapshot_download()` calls use `local_files_only=True`
- lm-eval task downloads disabled

---

## 8. Kaizen Agents (4 Alignment-Specific)

### AlignmentStrategistAgent
```python
class AlignmentStrategistSignature(Signature):
    use_case_description: str = InputField(...)
    base_model_id: str = InputField(...)
    training_data_description: str = InputField(..., default="")
    constraints: str = InputField(..., default="")

    recommended_method: str = OutputField(description="sft, dpo, or sft_then_dpo")
    lora_config_recommendation: str = OutputField(description="JSON LoRA config")
    data_requirements: str = OutputField(description="Format, size, quality criteria")
    training_timeline: str = OutputField(description="Estimated time and sessions")
    risks: str = OutputField(description="Overfitting, data quality, serving constraints")
    confidence: float = OutputField(description="0-1")
```

**Tools**: `get_base_model_info_tool(model_id)`, `list_training_methods_tool()`, `estimate_training_cost_tool(model_id, dataset_size, method)`

### DataCurationAgent
```python
class DataCurationSignature(Signature):
    dataset_stats: str = InputField(...)
    quality_report: str = InputField(...)
    target_use_case: str = InputField(...)

    quality_assessment: str = OutputField(...)
    curation_steps: list[str] = OutputField(...)
    minimum_viable_size: str = OutputField(...)
    confidence: float = OutputField(...)
```

**Tools**: `get_dataset_stats_tool(dataset_ref)`, `check_preference_quality_tool(dataset_ref)`

### TrainingConfigAgent
```python
class TrainingConfigSignature(Signature):
    model_id: str = InputField(...)
    dataset_size: int = InputField(...)
    gpu_memory_gb: float = InputField(...)
    objective: str = InputField(...)

    recommended_config: str = OutputField(description="JSON AlignmentConfig")
    memory_analysis: str = OutputField(...)
    training_time_estimate: str = OutputField(...)
    confidence: float = OutputField(...)
```

**Tools**: `get_gpu_memory_tool()`, `estimate_lora_memory_tool(model_id, lora_rank)`, `list_quantization_options_tool()`

### EvalInterpreterAgent
```python
class EvalInterpreterSignature(Signature):
    eval_results_json: str = InputField(...)
    original_objective: str = InputField(...)
    base_model_scores_json: str = InputField(..., default="{}")

    performance_assessment: str = OutputField(...)
    recommendation: str = OutputField(description="deploy, retrain, collect_more_data, investigate")
    next_steps: list[str] = OutputField(...)
    confidence: float = OutputField(...)
```

---

## 9. Dependencies Complete List

### Base (pip install kailash-align)

| Package | Version | Purpose |
|---------|---------|---------|
| kailash | >=1.0 | Core SDK |
| kailash-ml | >=1.0 | ModelRegistry (AdapterRegistry extends it) |
| kailash-kaizen | >=1.0 | KaizenModelBridge, Delegate |
| torch | >=2.2 | PyTorch (model loading, training) |
| transformers | >=4.40 | AutoModelForCausalLM, AutoTokenizer |
| trl | >=0.8 | SFTTrainer, DPOTrainer |
| peft | >=0.10 | LoRA/QLoRA adapter management |
| accelerate | >=0.28 | Multi-GPU/DeepSpeed/FSDP |
| datasets | >=2.18 | HuggingFace datasets for preference data |
| lm-eval | >=0.4 | Language model evaluation harness |

### [rlhf] Extra

| Package | Version | Purpose |
|---------|---------|---------|
| bitsandbytes | >=0.43 | 4-bit/8-bit quantization for QLoRA |

### [serve] Extra

No Python package dependencies. Ollama and vLLM are external binaries managed by the user.
