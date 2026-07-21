---
id: "S35-KAILASH-ALIGN"
name: kailash-align
description: "Kailash Align — MANDATORY for LLM fine-tuning/alignment/serving. Raw TRL/PEFT BLOCKED."
---

# Kailash Align - LLM Fine-Tuning & Alignment

LLM fine-tuning and alignment framework built on TRL (Transformer Reinforcement Learning). 12 supported methods, LoRA adapter management, evaluation-before-serving, and deployment to Ollama/vLLM.

**Python-only for v1** — GPU required for training.

## Install

```
pip install kailash-align           # Core (torch, transformers, trl>=1.0, peft)
pip install kailash-align[rlhf]     # + QLoRA (bitsandbytes)
pip install kailash-align[eval]     # + benchmarks (lm-eval)
pip install kailash-align[serve]    # + GGUF/Ollama (llama-cpp-python, gguf)
pip install kailash-align[online]   # + fast generation (vllm, CUDA only)
pip install kailash-align[full]     # Everything
```

## 12 Supported Methods

| Category       | Methods                                   | Data Format                   | Reward Needed           |
| -------------- | ----------------------------------------- | ----------------------------- | ----------------------- |
| **offline**    | sft, dpo, cpo                             | text / prompt+chosen+rejected | No                      |
| **unpaired**   | kto, bco                                  | prompt+completion+label       | No                      |
| **monolithic** | orpo                                      | prompt+chosen+rejected        | No                      |
| **online**     | grpo, rloo, ppo, online_dpo, xpo, nash_md | prompt only                   | Yes (except online_dpo) |

Special combo: `sft_then_dpo` — two-stage SFT then DPO with adapter chaining.

## Quick Start

```python
from kailash_align import AlignmentConfig, AlignmentPipeline

config = AlignmentConfig(
    method="dpo",
    base_model_id="meta-llama/Llama-3.1-8B",
)

pipeline = AlignmentPipeline(config=config)
result = await pipeline.train(dataset=preference_dataset, adapter_name="my-dpo-adapter")
# result.adapter_id, result.metrics, result.training_time
```

## Pipeline: config --> train --> evaluate --> serve

```
AlignmentConfig
      │
      ▼
AlignmentPipeline.train()
      │
      ▼
AlignmentEvaluator.evaluate()    ← MANDATORY before serving
      │
      ▼
AlignmentServing.deploy()        ← Ollama / vLLM / GGUF export
      │
      ▼
KaizenModelBridge.load()         ← Connect to Kaizen agents
```

**Eval-before-serve is mandatory.** No model reaches production without passing evaluation against the base model.

## 6 Core Engines

| Engine                 | Purpose                                      |
| ---------------------- | -------------------------------------------- |
| **AlignmentPipeline**  | Training orchestration via MethodRegistry    |
| **AdapterRegistry**    | LoRA adapter versioning + stage transitions  |
| **AlignmentEvaluator** | lm-eval-harness benchmarking                 |
| **AlignmentServing**   | GGUF export + Ollama + vLLM deployment       |
| **KaizenModelBridge**  | Connect fine-tuned models to Kaizen Delegate |
| **OnPremModelCache**   | Air-gapped model preparation                 |

## Method Selection Guide

| Scenario                                | Recommended Method | Why                                    |
| --------------------------------------- | ------------------ | -------------------------------------- |
| First fine-tune, have instruction data  | **sft**            | Simplest, most stable                  |
| Have preference pairs (chosen/rejected) | **dpo**            | No reward model needed, stable         |
| Want reasoning/math improvement         | **grpo**           | Group-relative optimization            |
| Limited preference data, have labels    | **kto**            | Works with binary labels, not pairs    |
| Want SFT + preference in one run        | **orpo**           | Combined objective, single training    |
| Need maximum control, have reward model | **ppo**            | Classic RLHF, most flexible            |
| Two-stage refinement                    | **sft_then_dpo**   | SFT baseline then preference alignment |

## Architecture

```
AlignmentConfig --> AlignmentPipeline --> MethodRegistry --> TRL Trainer
                                              │
                                         _lazy_import()
                                              │
                                    SFTTrainer / DPOTrainer / GRPOTrainer / ...
```

All TRL trainers are lazy-imported via `_lazy_import()` — no heavy torch imports at module level.

## Security

- `trust_remote_code=False` on all model/tokenizer loading
- RewardRegistry: programmatic registration only (no pickle/eval/dynamic import)
- NaN/Inf validation on all numeric config fields via `math.isfinite()`
- Subprocess calls use list form (no `shell=True`)
- Model name validation via regex before subprocess calls
- Bounded registries: `max_adapters=10,000`, `max_versions_per_adapter=1,000`

## Config Validation

All config classes are `@dataclass(frozen=True)` with `__post_init__` validation:

```python
from kailash_align import AlignmentConfig
from kailash_align.configs import GRPOConfig

config = AlignmentConfig(
    method="grpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    grpo=GRPOConfig(num_generations=4, kl_coef=0.001),
    reward_funcs=["accuracy"],
    # bf16 and fp16 are mutually exclusive (validated in __post_init__)
    bf16=True,
)
```

## DPO Loss Variants

Set `AlignmentConfig.loss_type` to use DPO variants without new trainer code:

`ipo`, `simpo`, `robust`, `bco_pair`, `sppo_hard`, `aot`, `aot_pair`, `nca_pair`

```python
config = AlignmentConfig(
    method="dpo",
    base_model_id="meta-llama/Llama-3.1-8B",
    loss_type="simpo",  # SimPO variant of DPO
)
```

## Skill Files

- [align-training](align-training.md) — AlignmentConfig, AlignmentPipeline, method selection, QLoRA, dataset formats
- [align-evaluation](align-evaluation.md) — Evaluation workflow, ROUGE, win-rate, safety checks, eval-before-serve
- [align-serving](align-serving.md) — GGUF export, Ollama deployment, vLLM, KaizenModelBridge
- [align-adapter-registry](align-adapter-registry.md) — AdapterRegistry, adapter chaining, version tracking

## Critical Rules

- Eval-before-serve is mandatory — no model deployed without evaluation
- `trust_remote_code=False` always — no arbitrary code execution from model repos
- Reward functions use registry-based registration only — no pickle/eval/dynamic import
- Config classes are frozen dataclasses — immutable after creation
- bf16 and fp16 are mutually exclusive
- All numeric config fields validated with `math.isfinite()`

## Related Skills

- [34-kailash-ml](../34-kailash-ml/SKILL.md) — Classical ML lifecycle (FeatureStore, ModelRegistry)
- [04-kaizen](../04-kaizen/SKILL.md) — AI agent framework (KaizenModelBridge target)
- [03-nexus](../03-nexus/SKILL.md) — Multi-channel deployment
