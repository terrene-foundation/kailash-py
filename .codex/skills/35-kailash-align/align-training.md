# Align Training

AlignmentConfig, AlignmentPipeline, method-specific configuration, QLoRA quantization, and dataset format requirements.

## AlignmentConfig

Central configuration for all training runs. Frozen dataclass with `__post_init__` validation.

```python
from kailash_align import AlignmentConfig, AlignmentPipeline

config = AlignmentConfig(
    method="dpo",                              # One of 12 methods
    base_model_id="meta-llama/Llama-3.1-8B",  # HuggingFace model ID
    output_dir="./output",                     # Training output directory
    bf16=True,                                 # bfloat16 (mutually exclusive with fp16)
    learning_rate=5e-5,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    lora_r=16,                                 # LoRA rank
    lora_alpha=32,                             # LoRA alpha
    lora_dropout=0.05,
)
```

### Method-Specific Configs

Each method has an optional dedicated config class for method-specific parameters.

```python
from kailash_align.configs import (
    GRPOConfig, DPOConfig, SFTConfig, PPOConfig, KTOConfig,
)

# GRPO (reasoning/math)
config = AlignmentConfig(
    method="grpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    grpo=GRPOConfig(
        num_generations=4,       # Generations per prompt
        kl_coef=0.001,           # KL divergence coefficient
        temperature=0.7,
    ),
    reward_funcs=["accuracy"],   # Required for online methods
)

# DPO with loss variant
config = AlignmentConfig(
    method="dpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    dpo=DPOConfig(beta=0.1),
    loss_type="simpo",           # SimPO variant
)

# PPO (classic RLHF)
config = AlignmentConfig(
    method="ppo",
    base_model_id="meta-llama/Llama-3.1-8B",
    ppo=PPOConfig(
        kl_penalty="kl",
        init_kl_coef=0.2,
    ),
    reward_funcs=["helpfulness"],
)

# SFT then DPO (two-stage)
config = AlignmentConfig(
    method="sft_then_dpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    sft=SFTConfig(num_train_epochs=1),
    dpo=DPOConfig(beta=0.1),
)
```

## AlignmentPipeline

Orchestrates training via MethodRegistry. Lazy-imports TRL trainers to avoid heavy imports at module level.

```python
pipeline = AlignmentPipeline(config=config)
result = await pipeline.train(
    dataset=dataset,
    adapter_name="my-adapter",
)

# result.adapter_id       — registered in AdapterRegistry
# result.metrics           — training metrics
# result.training_time     — duration in seconds
# result.total_params      — trainable parameter count
# result.adapter_path      — path to saved adapter weights
```

## QLoRA Setup

QLoRA enables fine-tuning large models on consumer GPUs by combining 4-bit quantization with LoRA adapters.

```python
from kailash_align import AlignmentConfig

config = AlignmentConfig(
    method="dpo",
    base_model_id="meta-llama/Llama-3.1-70B",
    # QLoRA quantization
    load_in_4bit=True,              # 4-bit quantization (requires bitsandbytes)
    bnb_4bit_compute_dtype="bf16",  # Compute in bfloat16
    bnb_4bit_quant_type="nf4",      # NormalFloat4 quantization
    # LoRA parameters
    lora_r=64,                       # Higher rank for larger models
    lora_alpha=128,
    lora_dropout=0.05,
    lora_target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
)

# Requires: pip install kailash-align[rlhf]  (includes bitsandbytes)
```

### GPU Memory Estimates (QLoRA)

| Model Size | GPU Memory (4-bit) | GPU Memory (Full) |
| ---------- | ------------------ | ----------------- |
| 7-8B       | ~6 GB              | ~32 GB            |
| 13B        | ~10 GB             | ~52 GB            |
| 70B        | ~40 GB             | ~280 GB           |

## Dataset Formats

Each method category expects a specific dataset format.

### SFT (Supervised Fine-Tuning)

```python
# Simple text format
sft_dataset = [
    {"text": "Below is an instruction...\n\nResponse: ..."},
    {"text": "Below is an instruction...\n\nResponse: ..."},
]

# Chat format (recommended)
sft_dataset = [
    {"messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing."},
        {"role": "assistant", "content": "Quantum computing uses..."},
    ]},
]
```

### DPO / CPO / ORPO (Preference Pairs)

```python
preference_dataset = [
    {
        "prompt": "Explain quantum computing simply.",
        "chosen": "Quantum computing uses quantum bits...",
        "rejected": "Quantum computing is a type of computing that...",
    },
]
```

### KTO / BCO (Binary Labels)

```python
binary_dataset = [
    {
        "prompt": "Explain quantum computing.",
        "completion": "Quantum computing uses quantum bits...",
        "label": True,   # Good completion
    },
    {
        "prompt": "Explain quantum computing.",
        "completion": "I don't know.",
        "label": False,  # Bad completion
    },
]
```

### GRPO / PPO / Online Methods (Prompts Only)

```python
prompt_dataset = [
    {"prompt": "Solve: What is 2+2?"},
    {"prompt": "Write a haiku about programming."},
]
# Reward function evaluates generated completions
```

## Reward Functions

Required for online methods (GRPO, PPO, RLOO, XPO, NASH_MD). Registered via RewardRegistry.

```python
from kailash_align.rewards import reward_registry

@reward_registry.register("accuracy")
def accuracy_reward(completions: list[str], prompts: list[str], **kwargs) -> list[float]:
    """Score completions based on correctness."""
    scores = []
    for completion, prompt in zip(completions, prompts):
        expected = extract_expected_answer(prompt)
        actual = extract_answer(completion)
        scores.append(1.0 if actual == expected else 0.0)
    return scores

@reward_registry.register("length_penalty")
def length_penalty(completions: list[str], **kwargs) -> list[float]:
    """Penalize overly long completions."""
    return [max(0.0, 1.0 - len(c) / 2000) for c in completions]

# Use in config
config = AlignmentConfig(
    method="grpo",
    reward_funcs=["accuracy", "length_penalty"],  # Multiple rewards combined
    ...
)
```

**Security**: Reward functions MUST be registered programmatically. No pickle, eval, or dynamic import of reward functions.

## Adding New Methods

1. Create `MethodConfig` with string-based TRL trainer reference
2. Call `register_method()` in `method_registry.py`
3. Optionally add frozen config dataclass with `to_trl_config()`
4. Add dataset validator and metrics extractor

```python
from kailash_align.method_registry import register_method

register_method(
    name="my_method",
    trainer_class="trl.MyMethodTrainer",
    dataset_format="preference",
    requires_reward=False,
)
```

## Critical Rules

- Config classes are `@dataclass(frozen=True)` — immutable after creation
- bf16 and fp16 are mutually exclusive — validated in `__post_init__`
- `math.isfinite()` on all numeric fields — NaN/Inf rejected
- `trust_remote_code=False` on all model loading — no arbitrary code execution
- Reward functions use registry only — no pickle/eval/dynamic import
- QLoRA requires `pip install kailash-align[rlhf]` for bitsandbytes
- Online methods require reward functions — offline methods do not
