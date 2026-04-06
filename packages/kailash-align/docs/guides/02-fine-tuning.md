# Fine-Tuning Methods

Choose and configure the right alignment method for your use case.

See also: [Method Selection Guide](../01-method-selection-guide.md) for the decision tree.

## SFT (Supervised Fine-Tuning)

Best for: instruction-following from text examples.

```python
from kailash_align.config import AlignmentConfig, SFTConfig

config = AlignmentConfig(
    method="sft",
    base_model_id="meta-llama/Meta-Llama-3-8B",
    sft=SFTConfig(
        num_train_epochs=3,
        per_device_train_batch_size=4,
        learning_rate=2e-4,
        max_seq_length=2048,
    ),
    lora=LoRAConfig(r=16, lora_alpha=32),
)
```

**Dataset format**: Each row has a `"text"` column with the full instruction+response.

## DPO (Direct Preference Optimization)

Best for: learning from human preference rankings.

```python
config = AlignmentConfig(
    method="dpo",
    base_model_id="meta-llama/Meta-Llama-3-8B",
    dpo=DPOConfig(
        beta=0.1,
        per_device_train_batch_size=2,
        learning_rate=5e-5,
    ),
)
```

**Dataset format**: Columns `"prompt"`, `"chosen"`, `"rejected"`.

## SFT then DPO (Combo)

Best for: when you have both instruction data and preference data.

```python
config = AlignmentConfig(
    method="sft_then_dpo",
    base_model_id="meta-llama/Meta-Llama-3-8B",
)

result = await pipeline.train(
    dataset=sft_dataset,
    adapter_name="my-adapter",
    preference_dataset=dpo_dataset,  # Required for sft_then_dpo
)
```

## GRPO (Group Relative Policy Optimization)

Best for: tasks with verifiable correctness (math, code).

```python
config = AlignmentConfig(
    method="grpo",
    base_model_id="meta-llama/Meta-Llama-3-8B",
)
```

**Requires**: reward functions registered in RewardRegistry.

## Hardware Requirements

| Model Size | Method    | Min GPU       | Recommended |
| ---------- | --------- | ------------- | ----------- |
| 1-3B       | SFT/DPO   | 8 GB          | 16 GB       |
| 7-8B       | SFT/DPO   | 16 GB (QLoRA) | 24 GB       |
| 7-8B       | GRPO/RLOO | 24 GB         | 48 GB       |
| 13B+       | Any       | 24 GB (QLoRA) | 80 GB       |

Use `estimate_training_memory()` for precise estimates:

```python
from kailash_align.gpu_memory import estimate_training_memory

estimate = estimate_training_memory(
    model_id="meta-llama/Meta-Llama-3-8B",
    lora_rank=16,
    batch_size=4,
    use_qlora=True,
)
print(f"Estimated VRAM: {estimate.total_estimate_gb:.1f} GB")
print(f"Fits in memory: {estimate.fits_in_memory}")
```

## Common Errors

**`TrainingError: sft_then_dpo requires preference_dataset`** -- Pass both `dataset` (SFT) and `preference_dataset` (DPO) to `pipeline.train()`.

**`CUDA out of memory`** -- Enable QLoRA (`use_qlora=True`), reduce batch size, or enable gradient checkpointing.
