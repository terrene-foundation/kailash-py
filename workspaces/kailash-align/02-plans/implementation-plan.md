# kailash-align Implementation Plan

## Prerequisites

kailash-align depends on kailash-ml's ModelRegistry (TSG-302). Implementation cannot begin until Phase 2 of kailash-ml is complete.

**Critical prerequisite (RT3-03)**: The ModelRegistry interface MUST be frozen in `kailash-ml-protocols` BEFORE kailash-align Phase 1 starts. This enables parallel prototyping with mock implementations.

## Red Team Round 1 Amendments

The following changes were incorporated from the analysis-phase red team (03-red-team-r1.md):

1. **RT3-02**: AlignmentServing must include post-conversion GGUF validation and "bring your own GGUF" escape hatch
2. **RT3-03**: ModelRegistry interface must be frozen in kailash-ml-protocols first (P0 blocker)
3. **RT3-04**: TRL version pin tightened to `>=0.25,<1.0` (was `>=0.8`)
4. **RT3-05**: All 4 agents deferred to v1.1 (saves 1 session; AlignmentStrategist and TrainingConfig are deterministic logic, not genuine agent reasoning)
5. **RT3-06**: lm-eval moved to `[eval]` optional extra; "quick" evaluation preset added

## Phase Overview

| Phase                                   | Workspaces                        | Sessions | Milestone                          |
| --------------------------------------- | --------------------------------- | -------- | ---------------------------------- |
| Phase 0: Interface contract             | (kailash-ml-protocols)            | 0.5      | Prerequisite                       |
| Phase 1: Bootstrap + AdapterRegistry    | WS-A1 (TSG-400)                   | 1        | M12-Align-Core                     |
| Phase 2: AlignmentPipeline              | WS-A2 (TSG-401)                   | 2-3      | M12-Align-Core                     |
| Phase 3: Evaluator + Serving (parallel) | WS-A3 (TSG-402) + WS-A4 (TSG-403) | 2-4      | M12-Align-Core / M13-Align-Serving |
| Phase 4: Bridge + On-Prem               | WS-A5 (TSG-404) + WS-A6 (TSG-406) | 1-2      | M13-Align-Serving                  |
| **Total**                               |                                   | **6-10** |                                    |

**Change from original**: Agents (TSG-405) deferred to v1.1, saving 1 session. Phase 4 reduced from 2-3 to 1-2 sessions.

## Phase 1: Bootstrap + AdapterRegistry (M12-Align-Core)

**Goal**: Standing package with AdapterRegistry extending ModelRegistry.

### Session 1

**TSG-400: Package bootstrap + AdapterRegistry** (P1, 1 session)

- Create `packages/kailash-align/` with standard layout
- `pyproject.toml` with all dependencies (torch, trl, peft, accelerate, datasets, transformers, lm-eval)
- `[rlhf]` extra: bitsandbytes
- `[serve]` extra: no Python deps
- `kailash_align/__init__.py` with lazy imports
- `AdapterRegistry` extending `ModelRegistry`:
  - `register_adapter()`: stores LoRA adapter metadata, base_model_id, merge_state
  - `list_adapters()`: filter by base_model_id
  - `get_adapter()`: returns AdapterVersion
  - `merge_adapter()`: uses peft.PeftModel.merge_and_unload()
- DataFlow models: AlignAdapter, AlignAdapterVersion
- `onnx_status = "not_applicable"` for all adapters
- Unit tests: register/get round-trip, list by base_model, merge_state transitions

**Exit criteria**: `pip install kailash-align` succeeds. AdapterRegistry stores and retrieves adapter metadata. Lazy imports work.

## Phase 2: AlignmentPipeline (M12-Align-Core)

**Goal**: SFT + DPO training pipeline works end-to-end.

**Prerequisite**: Phase 1 complete (AdapterRegistry exists).

### Session 2-4

**TSG-401: AlignmentPipeline** (P1, 2-3 sessions)

- `train()` with 3 methods: "sft", "dpo", "sft_then_dpo"
- AlignmentConfig: method, lora_config, training_args, use_qlora, gradient_checkpointing, mixed_precision
- Base model loading with `local_files_only` for air-gapped environments
- LoRA application via `peft.LoraConfig`
- QLoRA: 4-bit loading via bitsandbytes (requires [rlhf] extra)
- SFT via `trl.SFTTrainer` (using `SFTConfig`, not deprecated `TrainingArguments`)
- DPO via `trl.DPOTrainer` (using `DPOConfig`, prompt/chosen/rejected format)
- **NOTE (RT3-04)**: Pin TRL to `>=0.25,<1.0`. Test against current TRL version (v0.29+).
- Checkpoint management: save/resume
- Memory optimization: gradient_checkpointing + mixed precision (bf16/fp16)
- Auto-register trained adapters in AdapterRegistry
- DataFlow: AlignExperiment model tracking
- AlignmentResult dataclass
- Unit tests: config validation, LoRA config structure
- Integration test (GPU-marked): SFT on 100-sample synthetic data, loss decreases

**Exit criteria**: Can fine-tune a base model with SFT, optionally followed by DPO. Adapters registered in AdapterRegistry. Checkpoints saved and resumable.

## Phase 3: Evaluator + Serving (M12/M13)

**Goal**: Evaluate fine-tuned models and deploy them to Ollama/vLLM.

**Prerequisite**: Phase 2 complete (trained adapter exists).

WS-A3 and WS-A4 can run in parallel (evaluator does not depend on serving or vice versa).

### Session 5 (Evaluator)

**TSG-402: AlignmentEvaluator** (P1, 1-2 sessions)

- `evaluate()` wraps lm-eval-harness `simple_evaluate()`
- **NOTE (RT3-06)**: lm-eval is an `[eval]` optional extra. AlignmentEvaluator raises ImportError with install instructions if missing.
- Standard tasks: mmlu, hellaswag, arc_easy, truthfulqa, winogrande
- **ADD (RT3-06)**: "quick" task preset (arc_easy + hellaswag + truthfulqa, limit=100, ~5 min total)
- Custom task evaluation with user-provided scoring_fn (uses transformers.pipeline directly, NOT lm-eval)
- `compare()` for two adapter versions
- Model loading: handles merged + separate adapters (lm-eval supports PEFT adapter loading natively)
- EvalResult + TaskResult dataclasses
- DataFlow: AlignEvalResult storage
- Air-gapped support: local_files_only propagated
- Unit tests: EvalConfig validation, EvalResult serialization
- Integration test (GPU): evaluate tiny model on arc_easy (100 samples)

### Session 5-6 (Serving)

**TSG-403: AlignmentServing** (P1, 1-2 sessions)

- `export_gguf()`: merge adapter if needed -> convert_hf_to_gguf.py -> quantize
- **ADD (RT3-02)**: Post-conversion GGUF validation -- load GGUF, run single-prompt inference, verify no crash
- **ADD (RT3-02)**: "Bring your own GGUF" escape hatch: `deploy_ollama(gguf_path=...)` bypasses conversion
- **ADD (RT3-02)**: Supported architecture allowlist with warnings for untested models
- Always produce F16 GGUF first, then quantize as separate step
- `deploy_ollama()`: export GGUF -> write Modelfile -> `ollama create` -> verify
- `generate_vllm_config()`: write JSON config + launch script
- `deploy()`: unified dispatch to above methods
- GGUF quantization: f16, q4_k_m (recommended), q8_0
- ServingConfig: target, quantization, system_prompt, ollama_host, llama_cpp_dir
- Consider Ollama REST API `/api/create` as alternative to subprocess
- Unit tests: Modelfile format, vLLM config validity
- Integration test (requires ollama): deploy_ollama on tiny model

**Exit criteria**: Fine-tuned model can be evaluated against MMLU/ARC benchmarks. Model can be exported to GGUF and deployed to Ollama with one call.

## Phase 4: Bridge + On-Prem (M13-Align-Serving)

**Goal**: Kaizen Delegate uses fine-tuned model. Air-gapped deployment works.

**Prerequisite**: Phase 3 complete (serving produces deployable models).

**NOTE (RT3-05)**: Agents (TSG-405) deferred to v1.1.

### Session 7-8

**TSG-404: KaizenModelBridge** (P1, 1 session)

- `get_delegate_config()`: returns Delegate construction args for ollama/vllm strategies
- `create_delegate()`: factory returning ready-to-use Delegate (uses existing OllamaStreamAdapter / OpenAIStreamAdapter)
- `discover_deployed_models()`: lists adapters via Ollama `/api/tags` REST endpoint
- Auto-detection: resolve_strategy() checks Ollama -> vLLM (defer `local_hf` to v1.1)
- No changes needed to Delegate or adapter system
- Unit tests: delegate config for each strategy, auto-detection logic
- Integration test (requires ollama): full cycle train -> deploy -> create_delegate -> generate

**TSG-405: Kaizen agents** -- **DEFERRED TO v1.1**

- 4 agents: AlignmentStrategistAgent, DataCurationAgent, TrainingConfigAgent, EvalInterpreterAgent
- Rationale: None required for core workflow. AlignmentStrategist/TrainingConfig encode deterministic logic. DataCuration/EvalInterpreter are optional value-add.

**TSG-406: On-prem workflow** (P2, 1 session)

- OnPremConfig dataclass
- OnPremModelCache: download, list, verify, cache_path
- `kailash-align-prepare` CLI (click-based): download, list, verify commands
- OnPremSetupGuide.generate_checklist() -> markdown deployment checklist
- All engines accept `onprem_config` parameter
- Integration test: download tiny model -> list -> verify -> load with offline_mode=True

**Exit criteria**: Kaizen Delegate uses fine-tuned model via Ollama. Air-gapped deployment checklist works.

---

## Dependency Graph Between Todos

```
TSG-302 (kailash-ml ModelRegistry) ← EXTERNAL DEPENDENCY
    |
    v
TSG-400 (bootstrap + AdapterRegistry)
    |
    +-- TSG-401 (AlignmentPipeline)
    |       |
    |       +-- TSG-402 (Evaluator) ----+
    |       |                            |
    |       +-- TSG-403 (Serving) ------+---> TSG-404 (KaizenModelBridge)
    |                                    |
    |                                    +---> TSG-405 (Kaizen agents)
    |                                    |
    +------------------------------------+---> TSG-406 (On-prem workflow)
```

## Effort Comparison

| Estimate Source                      | Effort            | Notes                                                                      |
| ------------------------------------ | ----------------- | -------------------------------------------------------------------------- |
| Original (dependency analysis WS-4C) | 1-2 sessions      | Before red team; did not include serving, on-prem, or AdapterRegistry      |
| Red team Round 1 revised             | 4-6 sessions      | Added complexity for RL/RLHF; still bundled classical RL                   |
| Red team Round 2 (journal 0036)      | 7-12 sessions     | After split to kailash-align; includes serving + on-prem + bridge          |
| Previous plan                        | 7-11 sessions     | Detailed breakdown per todo; Phase 3 parallel execution saves 1-2 sessions |
| **This plan (RT3 amended)**          | **6-10 sessions** | Agents deferred to v1.1 (saves 1 session); lm-eval made optional           |

The decrease from 7-11 to 6-10 comes from deferring agents to v1.1 and simplifying Phase 4. The upper bound could still reach 12 if GGUF conversion edge cases require extensive debugging (RT3-02, RT3-04).

## Success Criteria

| Criterion          | Measurement                                              |
| ------------------ | -------------------------------------------------------- |
| Package installs   | `pip install kailash-align` succeeds                     |
| SFT training       | SFT on synthetic data, loss decreases                    |
| DPO training       | DPO on preference pairs, loss decreases                  |
| Adapter round-trip | register_adapter -> get_adapter, all metadata preserved  |
| Evaluation         | lm-eval-harness runs on at least 1 benchmark             |
| GGUF export        | Adapter exported to GGUF format                          |
| Ollama deployment  | Model deployed and serving via Ollama                    |
| Kaizen integration | Delegate configured via KaizenModelBridge generates text |
| Air-gapped mode    | Model loads with offline_mode=True from local cache      |
