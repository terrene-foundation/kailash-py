# kailash-align

LLM fine-tuning and alignment framework for the Kailash platform. Part of the [Kailash Python SDK](https://github.com/terrene-foundation/kailash-py) by the Terrene Foundation.

## Overview

kailash-align provides structured LoRA/QLoRA fine-tuning with full lifecycle tracking:

- **AdapterRegistry** -- Track adapters from training through evaluation, merge, GGUF export, and deployment
- **AlignmentPipeline** -- Thin wrappers around TRL SFTTrainer and DPOTrainer with checkpoint management
- **AlignmentConfig** -- Validated configuration dataclasses with NaN/Inf protection

## Installation

```bash
pip install kailash-align
```

### Optional Extras

```bash
pip install kailash-align[rlhf]    # QLoRA via bitsandbytes
pip install kailash-align[eval]    # Model evaluation via lm-eval
pip install kailash-align[serve]   # GGUF export via llama-cpp-python
pip install kailash-align[all]     # All extras
```

## Quick Start

```python
from kailash_align import AlignmentConfig, AlignmentPipeline, AdapterRegistry

# Configure
config = AlignmentConfig(
    base_model_id="meta-llama/Llama-3.1-8B",
    method="sft",
)

# Track adapters
registry = AdapterRegistry()

# Train
pipeline = AlignmentPipeline(config=config, adapter_registry=registry)
result = await pipeline.train(dataset=my_dataset, adapter_name="my-adapter")

# Result includes adapter path, metrics, and registry version
print(result.adapter_path)
print(result.training_metrics)
```

## License

Apache 2.0 -- see [LICENSE](../../LICENSE).
