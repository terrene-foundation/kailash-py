# kailash-align Overview Brief

## What This Is

kailash-align is a NEW Python package for LLM fine-tuning and alignment. It is the 8th Kailash framework. It handles the complete lifecycle from supervised fine-tuning (SFT) through direct preference optimization (DPO), evaluation, and deployment to on-prem serving infrastructure (Ollama, vLLM).

**This is NOT kailash-rl.** DPO is not reinforcement learning. SFT is not reinforcement learning. The dominant fine-tuning methods in 2026 are supervised or preference-based. The name "align" accurately describes the technology: aligning model behavior with human preferences and task requirements.

**Install**: `pip install kailash-align` (base) | `pip install kailash-align[rlhf]` (+ QLoRA) | `pip install kailash-align[full]` (everything)

**Package location**: `packages/kailash-align/` in the kailash-py monorepo.

## Strategic Context

The strategic justification is **fine-tuning SLMs (small language models) for on-prem secured environments**. This means:

- Fine-tuning models like Llama-3-8B, Mistral-7B, Phi-3-3.8B, Qwen2.5-7B
- Deploying to infrastructure where internet access is limited or absent
- Serving via Ollama or vLLM on local GPU hardware
- Integrating fine-tuned models with Kaizen Delegate for AI agent workflows

**Serving IS v1 scope.** Training without deployment delivers half the value. The `align.deploy(model, target="ollama")` experience completes the pipeline.

## Key Decisions

### 1. Separate Package, Not kailash-ml Extra

kailash-align is a first-class Kailash framework, not a `kailash-ml[align]` extra. Reasons:

| Criterion | kailash-ml[extra] (rejected) | kailash-align (chosen) |
|-----------|------------------------------|----------------------|
| Identity | Confusing -- "ML" suggests tabular/classical | Clear -- "align" = LLM fine-tuning |
| Dependencies | Pollutes kailash-ml with TRL/transformers/PEFT | Clean separation |
| User persona | Different users: ML engineer vs tabular data scientist | Each package serves its persona |
| Engine coherence | Engines designed for supervised learning don't fit alignment | AlignmentPipeline, AdapterRegistry are purpose-built |

### 2. Dependencies

kailash-align depends on kailash-ml (for ModelRegistry, which AdapterRegistry extends). Full dependency chain:

```
kailash (core)
    +-- kailash-ml (ModelRegistry)
    +-- kailash-kaizen (KaizenModelBridge, Delegate)
kailash-align
    +-- kailash, kailash-ml, kailash-kaizen
    +-- torch, trl, peft, accelerate, datasets, transformers, lm-eval
    +-- [rlhf]: bitsandbytes (for QLoRA 4-bit quantization)
```

### 3. ONNX Does NOT Apply

LLM fine-tuned models cannot be served via ONNX Runtime (too large, no KV-cache, no continuous batching). All adapters have `onnx_status = "not_applicable"`. LLM serving uses:

- **GGUF** format for Ollama/llama.cpp
- **vLLM** for batched production inference
- **Kaizen Delegate** connecting to Ollama/vLLM endpoints

### 4. Air-Gapped Support Is v1

On-prem means potentially no internet. kailash-align provides:
- `OnPremModelCache` for pre-downloading base models
- `kailash-align-prepare` CLI for download/verify before air-gap
- `OnPremConfig(offline_mode=True)` switches all HuggingFace calls to local-only

## Engines

| Engine | Purpose | WS |
|--------|---------|------|
| AlignmentPipeline | SFT + DPO orchestration, checkpoint management, memory optimization | WS-A2 |
| AdapterRegistry | Extends ModelRegistry for LoRA/QLoRA adapters, base model references, merge state | WS-A1 |
| AlignmentEvaluator | lm-eval-harness wrapper, custom task evaluation, DataFlow-backed results | WS-A3 |
| AlignmentServing | GGUF export, Ollama deployment, vLLM config generation | WS-A4 |
| KaizenModelBridge | Fine-tuned model -> Kaizen Delegate discovery and auto-configuration | WS-A5 |
| OnPremModelCache | Local model cache management, offline HuggingFace Hub emulation | WS-A6 |

## Kaizen Agents

4 alignment-specific agents (distinct from kailash-ml's 6 agents):

| Agent | Purpose |
|-------|---------|
| AlignmentStrategistAgent | Recommends method (SFT/DPO/SFT+DPO), LoRA config, data requirements |
| DataCurationAgent | Reviews preference dataset quality, recommends curation steps |
| TrainingConfigAgent | Recommends AlignmentConfig based on model size, GPU memory, data size |
| EvalInterpreterAgent | Interprets evaluation results, recommends deploy/retrain/collect-more-data |

All agents emit `confidence: float`, use Kaizen Delegate pattern, tools are dumb data endpoints.

## The SLM Fine-Tuning Workflow

| Step | What Happens | kailash-align Component |
|------|-------------|------------------------|
| 1. Select base model | Choose from HuggingFace Hub or local cache | OnPremModelCache |
| 2. Prepare preference data | Curate (prompt, chosen, rejected) triplets | DataCurationAgent |
| 3. Configure LoRA | Define adapter rank, target modules, alpha | AlignmentStrategistAgent / AlignmentConfig |
| 4. SFT (optional) | Supervised fine-tuning on instruction data | AlignmentPipeline (trl.SFTTrainer) |
| 5. DPO training | Train on preference pairs | AlignmentPipeline (trl.DPOTrainer) |
| 6. Evaluate | Run benchmarks (MMLU, ARC, custom) | AlignmentEvaluator (lm-eval-harness) |
| 7. Export/quantize | GGUF for Ollama, config for vLLM | AlignmentServing |
| 8. Deploy | Serve via Ollama/vLLM on-prem | AlignmentServing.deploy_ollama() |
| 9. Integrate with Kaizen | Point Delegate at local model endpoint | KaizenModelBridge.create_delegate() |

## Framework Value-Add (vs. Raw TRL Scripts)

The framework adds genuine value in exactly three places (identified in journal 0036):

1. **Adapter and model version management**: Track which adapter was trained on which data, which base model, which hyperparameters. Register the resulting model so Kaizen can discover it. (AdapterRegistry)

2. **Training pipeline orchestration**: Wrap the SFT-then-DPO sequence into a reproducible pipeline with checkpointing, logging, and failure recovery. (AlignmentPipeline)

3. **Evaluation orchestration**: Run standardized benchmarks and store results alongside model metadata. (AlignmentEvaluator)

Everything else is either project-specific (data curation, model selection, hyperparameters) or handled by external tools (Ollama, vLLM, llama.cpp). The framework does not try to own the entire workflow -- it orchestrates and tracks.

## Red Team Findings Incorporated

- **RT2-01** (CRITICAL, identity confusion): Replaced kailash-rl with kailash-align + kailash-ml[rl]. This is the defining decision.
- **RT2-02** (CRITICAL, dependency bloat): kailash-align's ~2.5GB install is unavoidable for LLM work. But it is isolated -- classical RL users install kailash-ml[rl] at ~505MB instead.
- **RT2-03** (CRITICAL, serving gap): Serving IS v1 scope. WS-A4 provides GGUF export + Ollama deployment + vLLM config.
- **RT2-04** (HIGH, effort underestimation): 7-12 sessions estimated (vs. original 1-2 for "WS-4C"). This is because serving, on-prem workflow, and AdapterRegistry are non-trivial.
- **RT2-05** (HIGH, missing dependencies): PEFT, accelerate, bitsandbytes, datasets, lm-eval-harness all listed in pyproject.toml.
- **Journal 0039 Gap 2**: kailash-ml confirmed as dependency (for ModelRegistry).
- **Journal 0039 Gap 3**: Serving confirmed as v1 scope.
