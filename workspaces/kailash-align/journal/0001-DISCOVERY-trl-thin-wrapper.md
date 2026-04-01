---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T10:00:00+08:00
author: agent
session_turn: 1
project: kailash-align
topic: AlignmentPipeline is a thin TRL wrapper; value lives in lifecycle management
phase: analyze
tags: [trl, alignment-pipeline, value-proposition, architecture]
---

# AlignmentPipeline Is a Thin TRL Wrapper

## Discovery

Deep analysis of TRL's SFTTrainer and DPOTrainer APIs (v0.29+, March 2026) reveals that AlignmentPipeline's core training methods (`_run_sft()`, `_run_dpo()`) are 3-5 line wrappers over TRL trainers. TRL already handles: LoRA/QLoRA integration, gradient checkpointing, mixed precision, multi-GPU via Accelerate, checkpoint saving/resuming, and chat template formatting.

AlignmentPipeline adds **zero training logic** beyond what TRL provides natively.

## Where Value Actually Lives

The framework's value is NOT in training. It is in three pillars:

1. **AdapterRegistry**: Version management for LoRA adapters (which adapter, which base model, which config, which data). No equivalent exists in the TRL ecosystem.
2. **AlignmentServing**: Automating the 7-step manual GGUF export + Ollama deployment pipeline. Error-prone when done manually.
3. **Lifecycle orchestration**: Connecting training output to evaluation, evaluation to deployment, deployment to Kaizen Delegate.

If kailash-align only did training, it should not exist as a package. The lifecycle management justifies it.

## Implications

- AlignmentPipeline code should be kept minimal (thin orchestrator, not a training framework)
- TRL version pinning is critical -- API changed between v0.8 and v0.29 (SFTConfig/DPOConfig introduced)
- The architecture doc pins `trl>=0.8` which is too loose; `>=0.25,<1.0` recommended

## For Discussion

1. Given that AlignmentPipeline's training code is essentially `trainer = SFTTrainer(...); trainer.train()`, should it be simplified to a utility function rather than a class with async methods?
2. If TRL had not introduced SFTConfig/DPOConfig (replacing TrainingArguments), would the version pinning risk have been caught before implementation?
3. How does the "thin wrapper with lifecycle value" pattern compare to kailash-ml's TrainingPipeline -- is that also primarily a thin wrapper over scikit-learn/Lightning?
