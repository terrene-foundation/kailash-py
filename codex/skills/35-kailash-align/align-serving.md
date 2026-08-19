# Align Serving

Model serving after fine-tuning: GGUF export for local deployment, Ollama integration, vLLM for high-throughput serving, and KaizenModelBridge for loading fine-tuned models into Kaizen agents.

## AlignmentServing

Central serving engine. Requires an evaluation result — deploy refuses without it (eval-before-serve is mandatory).

```python
from kailash_align.serving import AlignmentServing

serving = AlignmentServing()
```

## GGUF Export

Convert fine-tuned models to GGUF format for efficient local inference via llama.cpp and Ollama.

```python
# Export to GGUF (requires pip install kailash-align[serve])
gguf_path = await serving.export_gguf(
    adapter_id=train_result.adapter_id,
    output_path="./models/my-model.gguf",
    quantization="q4_k_m",    # Quantization method
)
```

### Quantization Options

| Method   | Size vs Original | Quality    | Use Case                       |
| -------- | ---------------- | ---------- | ------------------------------ |
| `q4_k_m` | ~25%             | Good       | Default, balanced              |
| `q5_k_m` | ~33%             | Very good  | Quality-sensitive tasks        |
| `q8_0`   | ~50%             | Excellent  | Maximum quality, more RAM      |
| `q3_k_m` | ~20%             | Acceptable | Minimal RAM, some quality loss |
| `f16`    | ~50%             | Lossless   | No quantization loss           |

```python
# High-quality export
gguf_path = await serving.export_gguf(
    adapter_id=train_result.adapter_id,
    output_path="./models/my-model-q5.gguf",
    quantization="q5_k_m",
)

# Minimal size export
gguf_path = await serving.export_gguf(
    adapter_id=train_result.adapter_id,
    output_path="./models/my-model-q3.gguf",
    quantization="q3_k_m",
)
```

## Ollama Deployment

Deploy fine-tuned models directly to a local or remote Ollama instance.

```python
# Deploy to Ollama (single command)
await serving.deploy(
    adapter_id=train_result.adapter_id,
    eval_result=eval_result,        # MANDATORY — deploy refuses without this
    target="ollama",
    model_name="my-fine-tuned-model",
)

# Model is now available via Ollama
# ollama run my-fine-tuned-model
```

### Ollama Deployment Flow

```
Adapter weights
      │
      ▼
Merge adapter into base model
      │
      ▼
Export to GGUF (q4_k_m default)
      │
      ▼
Generate Modelfile
      │
      ▼
ollama create my-model -f Modelfile
      │
      ▼
Model available: ollama run my-model
```

### Custom Ollama Configuration

```python
await serving.deploy(
    adapter_id=train_result.adapter_id,
    eval_result=eval_result,
    target="ollama",
    model_name="my-model",
    quantization="q5_k_m",          # Override default quantization
    system_prompt="You are a helpful coding assistant.",
    ollama_host="http://gpu-server:11434",  # Remote Ollama instance
    parameters={
        "temperature": 0.7,
        "top_p": 0.9,
        "num_ctx": 4096,
    },
)
```

## vLLM Deployment

High-throughput serving for production workloads. Requires `pip install kailash-align[online]`.

```python
await serving.deploy(
    adapter_id=train_result.adapter_id,
    eval_result=eval_result,
    target="vllm",
    host="0.0.0.0",
    port=8000,
    tensor_parallel_size=2,     # Multi-GPU serving
    max_model_len=4096,
)

# Generates launch script and starts vLLM server
# API compatible with OpenAI format:
# curl http://localhost:8000/v1/completions -d '{"model": "my-model", "prompt": "Hello"}'
```

### vLLM with LoRA Adapters

vLLM can serve the base model with multiple LoRA adapters simultaneously, switching per-request.

```python
await serving.deploy(
    adapter_id=train_result.adapter_id,
    eval_result=eval_result,
    target="vllm",
    enable_lora=True,
    max_lora_rank=64,
    # Multiple adapters can be loaded and selected per-request
)
```

### Shell Script Hardening

Generated vLLM launch scripts (`launch_vllm.sh`) follow security rules:

- Adapter names sanitized: regex `[^\w.:-]` replaced
- Subprocess calls use `shell=False` list form
- `--` separator before path arguments prevents flag injection

## KaizenModelBridge

Connect fine-tuned models to Kaizen agents. Allows Delegate and BaseAgent to use your fine-tuned model as their LLM backend.

```python
from kailash_align.serving import KaizenModelBridge

# Load fine-tuned model into Kaizen
bridge = KaizenModelBridge()
model_config = await bridge.load(
    adapter_id=train_result.adapter_id,
    eval_result=eval_result,         # Required
    backend="ollama",                # or "vllm"
)

# Use with Kaizen Delegate
from kaizen_agents import Delegate

delegate = Delegate(
    model=model_config.model_name,
    llm_provider=model_config.provider,  # "ollama" or "openai" (vLLM uses OpenAI-compatible API)
    **model_config.provider_kwargs,
)

async for event in delegate.run("Analyze this code"):
    print(event)
```

### Bridge with vLLM Backend

```python
model_config = await bridge.load(
    adapter_id=train_result.adapter_id,
    eval_result=eval_result,
    backend="vllm",
    vllm_url="http://localhost:8000",
)

# vLLM exposes OpenAI-compatible API
# provider="openai" with base_url pointed to vLLM
delegate = Delegate(
    model=model_config.model_name,
    llm_provider="openai",
    provider_config={"base_url": "http://localhost:8000/v1"},
)
```

## OnPremModelCache

Prepare models for air-gapped environments where internet access is unavailable.

```python
from kailash_align.serving import OnPremModelCache

cache = OnPremModelCache(cache_dir="/mnt/models")

# Download and cache model + tokenizer
await cache.prepare(
    model_id="meta-llama/Llama-3.1-8B",
    adapter_id=train_result.adapter_id,
)

# Later, in air-gapped environment:
config = AlignmentConfig(
    method="dpo",
    base_model_id="/mnt/models/meta-llama/Llama-3.1-8B",  # Local path
)
```

## Deployment Decision Guide

| Scenario                           | Target     | Why                                    |
| ---------------------------------- | ---------- | -------------------------------------- |
| Local development, single user     | **ollama** | Simple, low overhead                   |
| Production API, high throughput    | **vllm**   | Batching, multi-GPU, OpenAI-compatible |
| Kaizen agent backend               | **bridge** | Direct integration with Delegate       |
| Air-gapped / on-premise            | **cache**  | Pre-download, no internet needed       |
| Edge deployment, minimal resources | **gguf**   | Export only, bring your own runtime    |

## Critical Rules

- `deploy()` requires `eval_result` — no model served without evaluation
- GGUF `q4_k_m` is the default quantization — balanced quality and size
- vLLM launch scripts are sanitized — no shell injection via adapter names
- `trust_remote_code=False` maintained through the entire serving pipeline
- KaizenModelBridge requires eval_result — same mandatory eval gate
- OnPremModelCache downloads everything needed for offline operation
