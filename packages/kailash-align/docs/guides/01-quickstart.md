# Quickstart

Install kailash-align and fine-tune a model with QLoRA in under 10 minutes.

## Install

```bash
pip install kailash-align
```

For RLHF/QLoRA: `pip install kailash-align[rlhf]`
For evaluation: `pip install kailash-align[eval]`
For local serving: `pip install kailash-align[serve]`

## Fine-Tune with QLoRA

```python
from kailash_align.config import AlignmentConfig, LoRAConfig
from kailash_align.pipeline import AlignmentPipeline

config = AlignmentConfig(
    method="sft",
    base_model_id="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    use_qlora=True,
    lora=LoRAConfig(r=16, lora_alpha=32, lora_dropout=0.05),
)

pipeline = AlignmentPipeline(config)
result = await pipeline.train(
    dataset=your_sft_dataset,  # HuggingFace Dataset with "text" column
    adapter_name="my-first-adapter",
)
print(f"Adapter saved at: {result.adapter_path}")
print(f"Training loss: {result.metrics.get('train_loss', 'N/A')}")
```

## Evaluate

```python
from kailash_align.evaluator import AlignmentEvaluator
from kailash_align.config import EvalConfig

evaluator = AlignmentEvaluator()
eval_result = await evaluator.evaluate(
    adapter_name="my-first-adapter",
    config=EvalConfig(tasks=["hellaswag", "arc_easy"], limit=50),
)
for task in eval_result.tasks:
    print(f"  {task.name}: {task.score:.3f}")
```

## Deploy to Ollama

```python
from kailash_align.serving import AlignmentServing

serving = AlignmentServing()
await serving.deploy(
    adapter_name="my-first-adapter",
    target="ollama",
    quantization="q4_k_m",
)
# Model is now available via: ollama run my-first-adapter
```

## Common Errors

**`ImportError: bitsandbytes not found`** -- QLoRA requires bitsandbytes. Install with `pip install kailash-align[rlhf]`.

**`CUDA out of memory`** -- Reduce batch size in SFTConfig or use a smaller base model. See the [fine-tuning guide](02-fine-tuning.md) for memory optimization.

**`ValueError: base_model_id is required`** -- AlignmentConfig requires a HuggingFace model ID. Example: `"TinyLlama/TinyLlama-1.1B-Chat-v1.0"`.
