# Serving

Deploy fine-tuned models to Ollama, vLLM, or GGUF files.

## GGUF Export

Convert adapters to GGUF format for local inference:

```python
from kailash_align.serving import AlignmentServing

serving = AlignmentServing()

# Export as GGUF with 4-bit quantization
await serving.export_gguf(
    adapter_name="my-adapter",
    quantization="q4_k_m",
    output_path="./my-adapter.gguf",
)
```

### Quantization Options

| Format | Bits | Quality    | Size (7B model) |
| ------ | ---- | ---------- | --------------- |
| f16    | 16   | Best       | ~14 GB          |
| q8_0   | 8    | Very good  | ~7 GB           |
| q4_k_m | 4    | Good       | ~4 GB           |
| q4_k_s | 4    | Acceptable | ~3.5 GB         |

## Deploy to Ollama

```python
await serving.deploy(
    adapter_name="my-adapter",
    target="ollama",
    quantization="q4_k_m",
)
# Model available via: ollama run my-adapter
```

Verify:

```bash
ollama run my-adapter "Hello, how are you?"
```

## Deploy to vLLM

For high-throughput serving:

```python
await serving.deploy(
    adapter_name="my-adapter",
    target="vllm",
)
# Starts OpenAI-compatible API at http://localhost:8000
```

## On-Prem / Air-Gapped Deployment

For environments without internet access:

```python
from kailash_align.config import AlignmentConfig, OnPremConfig
from kailash_align.onprem import OnPremSetupGuide

# 1. Generate deployment checklist (with internet)
checklist = OnPremSetupGuide.generate_checklist(
    models=["meta-llama/Meta-Llama-3-8B"],
    cache_dir="/models/cache",
)
print(checklist.to_markdown())

# 2. Pre-download models
# kailash-align-prepare download meta-llama/Meta-Llama-3-8B

# 3. Configure offline mode
config = AlignmentConfig(
    method="sft",
    base_model_id="meta-llama/Meta-Llama-3-8B",
    onprem=OnPremConfig(
        offline_mode=True,
        model_cache_dir="/models/cache",
    ),
)
```

## Common Errors

**`GGUFExportError: llama-cpp-python not found`** -- Install with `pip install kailash-align[serve]`.

**`OllamaConnectionError`** -- Ensure Ollama is running: `ollama serve`.

**`vLLMError: CUDA required`** -- vLLM requires a CUDA GPU. Use Ollama for CPU inference.
