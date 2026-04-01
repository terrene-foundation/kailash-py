---
name: kaizen-align-serving
description: "kailash-align patterns -- AdapterRegistry, AlignmentPipeline (SFT/DPO), serving (GGUF, Ollama, vLLM), KaizenModelBridge, OnPremModelCache"
---

# kailash-align: LLM Fine-Tuning and Alignment

kailash-align provides the fine-tuning, evaluation, and serving pipeline for LLMs. Uses composition over kailash-ml's ModelRegistry (HAS-A, not IS-A). All 4 planned agents are deferred to v1.1.

## Install

```bash
pip install kailash-align            # Core (registry, config, pipeline stub)
pip install kailash-align[train]     # + TRL, PEFT, transformers (SFT/DPO training)
pip install kailash-align[eval]      # + lm-eval-harness (evaluation)
pip install kailash-align[serve]     # + llama-cpp-python, gguf (GGUF export + Ollama deploy)
pip install kailash-align[all]       # Everything
```

## Architecture

```
AdapterRegistry  <-- composition over ModelRegistry
       |
AlignmentPipeline (TRL wrapper: SFT -> DPO)
       |
AlignmentEvaluator (lm-eval-harness)
       |
AdapterMerger (PEFT merge_and_unload)
       |
AlignmentServing (GGUF -> Ollama/vLLM)
       |
KaizenModelBridge (create_delegate for Kaizen agents)
```

## AdapterRegistry

Tracks LoRA/QLoRA adapters through their lifecycle: training -> evaluation -> merge -> GGUF export -> deployment. Uses composition (HAS-A ModelRegistry, not inheritance).

```python
from kailash_align import AdapterRegistry, AdapterSignature

registry = AdapterRegistry(model_registry=ml_registry)  # Optional cross-registry

# Register adapter after training
version = await registry.register_adapter(
    name="customer-support-v1",
    adapter_path="/models/cs-v1/adapter",
    signature=AdapterSignature(
        base_model_id="meta-llama/Llama-3-8B",
        base_model_revision="main",
        lora_rank=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj"],
    ),
    training_metrics={"loss": 0.42, "eval_loss": 0.51},
)

# Stage progression (monotonic)
await registry.promote(name="customer-support-v1", target_stage="production")
```

Stage transitions: `staging -> shadow -> production -> archived` (monotonic forward only).

## AlignmentConfig

```python
from kailash_align import AlignmentConfig, SFTConfig, DPOConfig, LoRAConfig

config = AlignmentConfig(
    sft=SFTConfig(
        learning_rate=2e-5,
        num_epochs=3,
        batch_size=4,
        max_seq_length=2048,
    ),
    dpo=DPOConfig(
        beta=0.1,
        learning_rate=5e-6,
        num_epochs=1,
    ),
    lora=LoRAConfig(
        rank=16,
        alpha=32,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        dropout=0.05,
    ),
)
```

All numeric fields validated with `math.isfinite()` -- NaN/Inf rejected at construction.

## AlignmentPipeline

Thin TRL wrapper supporting SFT then optional DPO chaining.

```python
from kailash_align import AlignmentPipeline

pipeline = AlignmentPipeline(config=config)
result = await pipeline.train(
    model_id="meta-llama/Llama-3-8B",
    dataset=sft_dataset,           # SFT stage
    dpo_dataset=preference_data,   # Optional DPO stage
)
# result.adapter_path, result.metrics, result.training_time
```

## AlignmentEvaluator

Wraps lm-eval-harness for standardized evaluation. Requires `[eval]` extra.

```python
from kailash_align import AlignmentEvaluator, EvalConfig

evaluator = AlignmentEvaluator(config=EvalConfig(preset="quick"))
result = await evaluator.evaluate(
    model_path="/models/cs-v1/merged",
    tasks=["hellaswag", "arc_easy"],
)
# result.task_results: dict[str, TaskResult]
# result.aggregate_score: float
```

## AlignmentServing

Handles GGUF export, Ollama deployment, and vLLM config generation.

```python
from kailash_align import AlignmentServing, ServingConfig

serving = AlignmentServing(
    adapter_registry=registry,
    config=ServingConfig(
        quantization="q4_k_m",          # GGUF quantization type
        ollama_model_name="cs-v1",      # Ollama model name
    ),
)

# Deploy to Ollama (export GGUF -> create Modelfile -> ollama create)
result = await serving.deploy(
    adapter_name="customer-support-v1",
    model_name="cs-v1",
)
# result["ollama_model"], result["gguf_path"]

# Generate vLLM config
vllm_config = await serving.generate_vllm_config(
    adapter_name="customer-support-v1",
)
```

Supported architectures: `LlamaForCausalLM`, `MistralForCausalLM`, `Phi3ForCausalLM`, `Qwen2ForCausalLM`.

## Adapter Merge

Merge LoRA adapter into base model using PEFT `merge_and_unload`.

```python
from kailash_align import AdapterMerger

merger = AdapterMerger()
merged_path = await merger.merge(
    base_model_id="meta-llama/Llama-3-8B",
    adapter_path="/models/cs-v1/adapter",
    output_path="/models/cs-v1/merged",
)
```

## KaizenModelBridge

Factory for creating Kaizen Delegates that use fine-tuned local models via Ollama or vLLM.

```python
from kailash_align import KaizenModelBridge, BridgeConfig

bridge = KaizenModelBridge(
    adapter_registry=registry,
    config=BridgeConfig(
        ollama_host="http://localhost:11434",
        vllm_endpoint="http://localhost:8000/v1",
    ),
)

# Create a Delegate using deployed fine-tuned model
delegate = await bridge.create_delegate(
    adapter_name="customer-support-v1",
    strategy="ollama",  # or "vllm", or None for auto-detect
)

# Use like any other Delegate
async for event in delegate.run("Help me with my order"):
    print(event)
```

**Budget note** (R2-04): Delegate's `budget_usd` tracking uses cloud API pricing. Local models (Ollama/vLLM) have $0/token cost. Use `max_turns` or `max_tokens` for execution bounds on local models instead of `budget_usd`.

## OnPremModelCache (Air-Gap Support)

Pre-download models for air-gapped environments.

```python
from kailash_align import OnPremModelCache, OnPremConfig

cache = OnPremModelCache(config=OnPremConfig(cache_dir="/models/cache"))

# Prepare (run with internet access)
await cache.prepare("meta-llama/Llama-3-8B")

# CLI equivalent
# kailash-align-prepare meta-llama/Llama-3-8B --cache-dir /models/cache
```

## Cross-References

- `packages/kailash-align/` -- Source code
- `skills/04-kaizen/kaizen-ml-integration.md` -- kailash-ml engine patterns
- `skills/02-dataflow/dataflow-ml-integration.md` -- DataFlow + ML integration
- `agents/frameworks/kaizen-specialist.md` -- Kaizen agent (covers ML + align)
