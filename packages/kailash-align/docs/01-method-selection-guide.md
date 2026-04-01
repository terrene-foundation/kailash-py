# Method Selection Guide

How to choose the right alignment method based on your data, compute budget, and goals.

## Decision Tree

```
                         START
                           |
                  What data do you have?
                 /         |          \
          Text only    Preferences    Reward functions
          (examples)   (rankings)     (verifiable correctness)
              |        /       \              |
             SFT   Paired?   Unpaired?     Online RL
              |      |          |          /        \
              |    Yes: do    Binary    Verifiable   General
              |    you want   labels    answers      quality
              |    SFT too?   (good/     (math,       |
              |    /    \      bad)      code)       RLOO
              |  Yes    No      |          |
              |   |      |     KTO       GRPO
              | sft_     |
              | then_  Need
              | dpo   single
              |       pass?
              |      /    \
              |    Yes    No
              |     |      |
              |   ORPO    DPO
              |
              +-- Want contrastive? --> CPO
              +-- Unpaired alt? -----> BCO
              +-- Exploration? ------> XPO (experimental)
              +-- Game-theoretic? ---> NashMD (experimental)
```

## Quick Reference: Which Method When

### I have instruction examples (input/output pairs)

Use **SFT** (Supervised Fine-Tuning). This is the foundation. Most workflows start here.

```python
# Data format: {"text": "### Instruction: ...\n### Response: ..."}
config = AlignmentConfig(method="sft", base_model_id="meta-llama/Llama-3.1-8B")
```

### I have paired preferences (prompt + chosen + rejected)

Use **DPO** for the standard approach. Use **ORPO** if you want to skip the SFT stage and do both in one pass. Use **sft_then_dpo** if you want the classic two-stage pipeline.

```python
# Data format: {"prompt": "...", "chosen": "...", "rejected": "..."}
config = AlignmentConfig(method="dpo", base_model_id="meta-llama/Llama-3.1-8B")
# Or: method="orpo" for single-pass
# Or: method="sft_then_dpo" for two-stage (also needs SFT dataset)
```

### I have binary feedback (thumbs up / thumbs down)

Use **KTO**. It works with unpaired binary signals -- each example is independently labeled good or bad, with no requirement that good and bad examples share the same prompt.

```python
# Data format: {"prompt": "...", "completion": "...", "label": True/False}
config = AlignmentConfig(method="kto", base_model_id="meta-llama/Llama-3.1-8B")
```

### I have reward functions (verifiable correctness, math, code)

Use **GRPO** (the method behind DeepSeek-R1). The model generates completions, reward functions score them, and the model improves beyond the quality of the training data.

```python
# Data format: {"prompt": "What is 2+2?"}
# Register reward function first:
from kailash_align import reward_registry

@reward_registry.register("math_check")
def math_check(completions, prompts, **kwargs):
    return [1.0 if "4" in c else 0.0 for c in completions]

config = AlignmentConfig(
    method="grpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    reward_funcs=["math_check"],
)
```

### I want to improve beyond SFT but have no preference data

Use **GRPO** with custom reward functions. You define what "good" means programmatically.

## Method Comparison Table

| Method           | Category   | Data Required                               | Compute Cost | When to Use                                                 |
| ---------------- | ---------- | ------------------------------------------- | ------------ | ----------------------------------------------------------- |
| **SFT**          | Offline    | Instruction examples (text)                 | Low          | Starting point. Teach the model a task format.              |
| **DPO**          | Offline    | Paired preferences (prompt/chosen/rejected) | Medium       | Standard preference alignment with human rankings.          |
| **CPO**          | Offline    | Paired preferences (prompt/chosen/rejected) | Medium       | Alternative to DPO with contrastive loss. Less common.      |
| **KTO**          | Unpaired   | Binary feedback (prompt/completion/label)   | Medium       | When you only have thumbs-up/down, not paired comparisons.  |
| **BCO**          | Unpaired   | Binary feedback (prompt/completion/label)   | Medium       | Alternative to KTO. Binary classifier approach.             |
| **ORPO**         | Monolithic | Paired preferences (prompt/chosen/rejected) | Medium       | SFT + preference in one pass. Saves time vs sft_then_dpo.   |
| **GRPO**         | Online     | Prompts + reward functions                  | High         | Improve beyond training data. Math, code, verifiable tasks. |
| **RLOO**         | Online     | Prompts + reward functions                  | High         | Alternative to GRPO with leave-one-out variance reduction.  |
| **Online DPO**   | Online     | Prompts (+ reward model)                    | High         | DPO with online generation. Requires reward model.          |
| **XPO**          | Online     | Prompts + reward functions                  | High         | Exploration-based. Experimental.                            |
| **NashMD**       | Online     | Prompts + reward functions                  | High         | Game-theoretic equilibrium. Experimental.                   |
| **sft_then_dpo** | Combo      | SFT data + preference data                  | Medium       | Classic two-stage: SFT first, then DPO.                     |

## Data Requirements Detail

### Offline and Monolithic Methods

| Method         | Required Columns               | Example                                                                  |
| -------------- | ------------------------------ | ------------------------------------------------------------------------ |
| SFT            | `text`                         | `{"text": "### Instruction: Summarize.\n### Response: Done."}`           |
| DPO, CPO, ORPO | `prompt`, `chosen`, `rejected` | `{"prompt": "Write a poem.", "chosen": "Roses...", "rejected": "Um..."}` |

### Unpaired Methods

| Method   | Required Columns                | Example                                                            |
| -------- | ------------------------------- | ------------------------------------------------------------------ |
| KTO, BCO | `prompt`, `completion`, `label` | `{"prompt": "Explain X.", "completion": "X is...", "label": true}` |

### Online Methods

| Method                  | Required Columns | Additional Requirement                          |
| ----------------------- | ---------------- | ----------------------------------------------- |
| GRPO, RLOO, XPO, NashMD | `prompt`         | Reward functions registered in `RewardRegistry` |
| Online DPO              | `prompt`         | Generation backend (vLLM or HF)                 |

## Compute Cost Guide

### Approximate GPU Memory (LoRA rank=16, seq_len=1024, batch_size=2)

| Method           | 3B     | 7B     | 13B    | 70B     |
| ---------------- | ------ | ------ | ------ | ------- |
| SFT              | ~8 GB  | ~16 GB | ~28 GB | ~140 GB |
| DPO/KTO/ORPO/CPO | ~10 GB | ~20 GB | ~34 GB | ~170 GB |
| GRPO/RLOO        | ~14 GB | ~28 GB | ~48 GB | ~240 GB |

Online methods (GRPO, RLOO) use more memory because they run generation during training.

### Hardware Recommendations

| GPU                               | Best For                                                                         |
| --------------------------------- | -------------------------------------------------------------------------------- |
| **NVIDIA A100 80GB**              | Any method, any model up to 13B. 70B with QLoRA.                                 |
| **NVIDIA A10G / RTX 4090 (24GB)** | SFT/DPO/KTO/ORPO up to 7B. GRPO up to 3B (or 7B with batch_size=1).              |
| **NVIDIA T4 (16GB)**              | SFT up to 3B with LoRA rank=8, batch_size=1. Not recommended for online methods. |
| **Apple Silicon (MPS)**           | SFT/DPO up to 3B. No vLLM (use HFGenerationBackend for online methods).          |

### Use `estimate_training_memory` to Check

```python
from kailash_align import estimate_training_memory

estimate = estimate_training_memory(
    model_id="meta-llama/Llama-3.1-8B",
    lora_rank=16,
    batch_size=2,
    is_online_method=True,  # Set True for GRPO/RLOO
)
print(f"Estimated: {estimate.total_estimate_gb:.1f} GB")
print(f"Fits: {estimate.fits_in_memory}")
print(f"Recommended batch size: {estimate.recommended_batch_size}")
```

## Method Selection by Goal

| Goal                               | Recommended Method  | Why                                          |
| ---------------------------------- | ------------------- | -------------------------------------------- |
| Teach a model a new format/task    | SFT                 | Direct supervised learning on examples       |
| Align with human preferences       | DPO or sft_then_dpo | Standard RLHF replacement                    |
| Align with minimal data collection | KTO                 | Only needs binary good/bad labels            |
| Single-pass alignment (save time)  | ORPO                | Combines SFT + preference in one pass        |
| Improve math/code reasoning        | GRPO                | Reward functions for verifiable correctness  |
| Explore beyond training data       | GRPO or XPO         | Online generation with reward scoring        |
| Production with limited time       | ORPO                | One training run instead of two              |
| Research / experimental            | XPO, NashMD         | Cutting-edge methods, less production-tested |
