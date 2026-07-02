# Red Team Report R1: Alignment/RL Expansion Analysis

**Scope**: Cross-workspace synthesis (12), method landscape (08), classical RL ecosystem (09), implementation audit (10), kailash-rs gap analysis (11)

**Date**: 2026-04-01

**Severity scale**: CRITICAL (blocks implementation), HIGH (will cause production failures), MEDIUM (design flaw, fixable), LOW (improvement opportunity)

---

## Finding C1: TRL Version Claim Errors — Phantom Trainers and Wrong Version Floors (CRITICAL)

### What the analysis claims

Document 10 (implementation audit) Section 6 lists TRL version requirements per trainer:

| Trainer      | Claimed Version |
| ------------ | --------------- |
| IPOTrainer   | `>=0.14.0`      |
| SimPOTrainer | `>=0.12.0`      |
| GRPOTrainer  | `>=0.13.0`      |
| KTOTrainer   | `>=0.14.0`      |

### What is wrong

**IPOTrainer and SimPOTrainer do not exist as separate classes in TRL.** Document 08 correctly identifies that IPO and SimPO are `loss_type` parameters on `DPOTrainer`, but document 10 lists them as separate trainers with their own version requirements. This contradiction is dangerous because it could lead to:

1. Implementation effort building wrappers for classes that do not exist
2. Incorrect version pinning

The synthesis (document 12) partially inherits this confusion. It correctly says "All via DPOTrainer `loss_type`" in the priority table, but the implementation audit's version table is the document that would be consulted during actual development.

**Additionally**: The version floors are anachronistic. The pyproject.toml pins `trl>=0.25,<1.0`. TRL 1.0 was released in late 2025 and restructured its API surface. The analysis references pre-1.0 experimental APIs (e.g., `GRPOConfig` in `>=0.13.0`) without verifying whether the post-1.0 API changed. The pin `trl>=0.25,<1.0` actually excludes TRL 1.0+, which is the version where GRPOTrainer and RLOOTrainer became **stable**. This means:

- The current pin locks out the stable API for GRPO and RLOO
- Users are stuck on TRL 0.x experimental surfaces that may have different parameter names

### Required action

1. Verify all trainer class names against TRL >=0.25 and TRL 1.0 documentation
2. Decide: pin `trl>=1.0,<2.0` (stable API, GRPO/RLOO promoted) or stay on `trl>=0.25,<1.0` (experimental API, potentially different signatures)
3. Remove phantom trainer references (IPOTrainer, SimPOTrainer as standalone classes) from all documents
4. Remove the version table from document 10 or replace with verified class-to-version mapping

---

## Finding C2: Reward Function Security — Arbitrary Code Execution Vector (CRITICAL)

### What the analysis misses entirely

All five documents discuss `reward_func` / `reward_funcs` as a callable that scores completions. None address the security implications.

GRPO, RLOO, and Online DPO accept **arbitrary Python callables** as reward functions:

```python
def accuracy_reward(completions, **kwargs) -> list[float]:
    return [1.0 if is_correct(c) else 0.0 for c in completions]

trainer = GRPOTrainer(
    model="...",
    reward_funcs=[accuracy_reward],  # User-supplied code
    ...
)
```

If kailash-align exposes a configuration API where users can specify reward functions by name, path, or serialized callable, this creates a **code injection surface**:

1. **Pickle deserialization**: If reward functions are serialized/deserialized (e.g., for distributed training or config persistence), `pickle.loads()` executes arbitrary code
2. **Dynamic import**: If the MethodRegistry allows `reward_func: "my_module:my_func"` as a string, `importlib.import_module()` loads arbitrary modules
3. **Eval/exec**: If reward function definitions are stored as strings in config files and evaluated, this is direct code injection

The proposed `MethodRegistry` design stores `Callable` references, but the analysis does not address:

- How reward functions are specified in `AlignmentConfig` (as Python objects? as strings? as file paths?)
- Whether reward functions can be persisted to disk and loaded later
- Whether multi-node distributed training sends reward functions across the wire
- Whether the CLI (`kailash-align-prepare`) could accept reward function specifications from user input

### Required action

1. Add a security section to the synthesis defining how reward functions are specified, validated, and sandboxed
2. Decide: reward functions as Python objects only (no serialization) vs. registered named functions (like TRL's approach) vs. file path + function name (needs import validation)
3. If any serialization is needed, use `inspect.getsource()` + AST validation, NEVER pickle
4. Document the threat model: who provides reward functions, what access do they have, what can they execute

---

## Finding C3: GPU Memory Analysis Missing for Online Methods (HIGH)

### What the analysis claims

Document 08 mentions GRPO "eliminates the critic (value) network required by PPO, reducing memory by ~50%" and SimPO saves "~50% GPU memory" vs. DPO. Document 12 mentions "reference-free methods save ~50% GPU memory."

### What is wrong

These are comparisons against other methods, not actual memory requirements for running GRPO/RLOO on kailash-align's target hardware. No document provides:

1. **Concrete memory estimates per method and model size**:
   - GRPO with `num_generations=16` on a 7B model: needs to generate 16 completions per prompt in a single batch. Even with sequential generation, this requires the full model in memory plus KV cache for 16 sequences simultaneously (or sequentially, trading time for memory)
   - With vLLM backend: vLLM manages its own GPU memory via PagedAttention, but the training model and vLLM inference engine coexist, requiring careful memory partitioning

2. **The "2x model copies" question**: GRPO in TRL can run in two modes:
   - **Without vLLM**: The training model generates completions itself. Only 1 model copy, but generation is slow
   - **With vLLM**: A separate vLLM server hosts the model for fast generation. The training process has its own copy for gradient updates. This IS 2x model memory, contradicting the "50% savings vs PPO" claim (PPO is 3x: policy + value + reference; GRPO-vLLM is 2x: policy + vLLM inference copy)

3. **QLoRA interaction**: The analysis assumes QLoRA (4-bit base + LoRA adapters) reduces memory uniformly, but does not consider that online methods generate completions through the quantized model, which may affect generation quality differently than offline methods

4. **Batch size implications**: GRPO's `num_generations` parameter multiplies memory linearly. DeepSeek-R1 used `num_generations=16`. On a 7B model with 2048 max_completion_length, each generation consumes ~4GB of KV cache. 16 simultaneous generations = 64GB of KV cache alone. This exceeds a single A100 80GB.

### Required action

1. Add a GPU memory analysis table: method x model_size x hardware = feasibility
2. Document the vLLM memory partitioning strategy (how much VRAM for training vs. inference)
3. Clarify whether kailash-align's default configuration is single-GPU or multi-GPU
4. Add warnings for configurations that exceed single-GPU memory (e.g., GRPO with num_generations=16 on 7B+ models without vLLM)
5. Consider whether `num_generations=2` (per the "2-GRPO" paper cited in document 08) should be the default to make single-GPU training feasible

---

## Finding C4: vLLM as Inference Backend — Completely Missing from Architecture (HIGH)

### What the analysis notes (but does not solve)

Document 08 correctly marks vLLM support per trainer:

| Trainer              | vLLM Support |
| -------------------- | ------------ |
| GRPOTrainer          | Yes          |
| RLOOTrainer          | Yes          |
| OnlineDPOTrainer     | Yes          |
| XPOTrainer           | Yes          |
| NashMDTrainer        | Yes          |
| All offline trainers | No           |

But the synthesis (document 12), implementation audit (document 10), and MethodRegistry design all ignore vLLM entirely. The proposed `MethodConfig` dataclass has:

```python
@dataclass
class MethodConfig:
    name: str
    trainer_class: type
    config_class: type
    dataset_validator: Callable
    dataset_required_columns: set[str]
    metrics_extractor: Callable
    requires_preference_data: bool
    requires_reference_model: bool
    supports_chaining: bool
```

Missing: `supports_vllm: bool`, `requires_generation_backend: bool`, or any indication that online methods need a generation infrastructure.

### Why this matters

vLLM is not optional for production GRPO. Without vLLM:

- Generation is 10-50x slower (vanilla HuggingFace `model.generate()` vs. PagedAttention + continuous batching)
- Training time for GRPO on a 7B model increases from hours to days
- The entire value proposition of GRPO (fast online RL) evaporates

TRL's GRPOTrainer has a `use_vllm` parameter and handles vLLM server lifecycle. kailash-align needs to:

1. Decide whether vLLM is a required or optional dependency for online methods
2. Add vLLM to pyproject.toml optional dependencies (it is currently absent)
3. Handle vLLM server startup/shutdown in the pipeline
4. Manage GPU memory split between vLLM server and training process

### Required action

1. Add `vllm>=0.6` to `[project.optional-dependencies]` (new extra, e.g., `[online]`)
2. Add vLLM lifecycle management to the online pipeline design
3. Update MethodConfig to include generation backend requirements
4. Document the GPU memory split strategy

---

## Finding H1: MethodRegistry Type Safety — `type` References Break Lazy Imports (HIGH)

### What the analysis proposes

Document 10 (Section 4.1.1) and document 12 propose:

```python
@dataclass
class MethodConfig:
    trainer_class: type  # TRL trainer
    config_class: type   # Config dataclass
    ...

METHOD_REGISTRY = {
    "grpo": MethodConfig(trainer_class=GRPOTrainer, ...),
}
```

### What is wrong

Storing `type` references in a module-level registry forces **eager import** of all TRL trainer classes at module load time. This contradicts the existing architecture's lazy import pattern:

```python
# Current: lazy import in _run_sft()
async def _run_sft(self, ...):
    from trl import SFTTrainer  # Only imported when SFT is actually used
```

A module-level `METHOD_REGISTRY` that contains `GRPOTrainer`, `KTOTrainer`, `ORPOTrainer` etc. would:

1. Import `trl` and all trainer submodules at `import kailash_align` time
2. Import `vllm` transitively (GRPOTrainer imports vLLM-related code)
3. Increase import time from ~100ms to 2-5 seconds
4. Fail at import time if optional dependencies (vLLM, bitsandbytes) are not installed

### Correct approach

Use string-based lazy references:

```python
@dataclass
class MethodConfig:
    trainer_module: str   # "trl"
    trainer_class_name: str  # "GRPOTrainer"
    config_class_name: str   # "GRPOConfig"
    ...

    def get_trainer_class(self) -> type:
        import importlib
        mod = importlib.import_module(self.trainer_module)
        return getattr(mod, self.trainer_class_name)
```

Or use a factory function pattern that defers import until `train()` is called.

### Required action

1. Redesign MethodRegistry to use string-based lazy references, not type objects
2. Ensure `import kailash_align` does not trigger TRL imports
3. Test that kailash-align remains importable without optional dependencies (vLLM, bitsandbytes, lm-eval)

---

## Finding H2: ORPO Data Format Claim Is Incorrect (HIGH)

### What the analysis claims

Document 10 (Section 3.A) states:

> "ORPO needs `margin` column"

Document 12 lists ORPO alongside DPO with the same data format:

> `{prompt, chosen, rejected}` — DPO, IPO, CPO, SimPO, NCA, ORPO

### What is wrong

Document 10 contradicts document 12. The correct answer is that **ORPO uses the same data format as DPO** (`{prompt, chosen, rejected}`). There is no `margin` column. The ORPO paper's "margin" refers to the mathematical formulation (log odds ratio margin), not a data column.

Document 10's claim that "ORPO needs `margin` column" would lead to:

- Building an unnecessary data validator that rejects valid ORPO datasets
- Confusing users who try to use standard preference datasets with ORPO
- Creating a fictional data format requirement

### Required action

1. Remove the claim that ORPO needs a `margin` column from document 10
2. Verify all data format claims against actual TRL trainer `__init__` signatures
3. The dataset validator for ORPO should accept `{prompt, chosen, rejected}` (same as DPO)

---

## Finding H3: Phasing Has a Dependency Inversion — Phase A Cannot Be Validated Without Phase B Infrastructure (HIGH)

### What the synthesis proposes (document 12)

- **Phase A**: Add `loss_type` to AlignmentConfig (1 session)
- **Phase B**: MethodRegistry + generic trainer (2-3 sessions)
- **Phase C**: Online RL methods (2-3 sessions)

### What is wrong

Phase A says "Add `loss_type` to AlignmentConfig" and "Update method validation to accept all TRL-supported methods." But the current `AlignmentConfig.__post_init__` does:

```python
if self.method not in ("sft", "dpo", "sft_then_dpo"):
    raise ValueError(...)
```

Adding `loss_type` to `DPOConfig` is indeed trivial (one field). But "Update method validation to accept all TRL-supported methods" means changing the `method` enum to accept `"kto"`, `"orpo"`, `"grpo"`, etc. If you do this in Phase A without the Phase B infrastructure (MethodRegistry, generic trainer, data validators), then:

1. `AlignmentConfig(method="grpo")` will pass validation
2. `pipeline.train()` will hit the `else: raise TrainingError("Unknown training method")` branch
3. Users see: config validates, training crashes

This is a **validation-implementation gap**. Either:

- Phase A should NOT expand the `method` enum (only add `loss_type` to DPOConfig)
- Phase A should include the minimal Phase B infrastructure to handle the new methods

Additionally, Phase A says "Update AdapterSignature to accept dynamic method names" — but AdapterSignature is used in the registry to record what method trained an adapter. If you accept arbitrary method names in AdapterSignature before the MethodRegistry exists, you lose the ability to validate that the method name is real.

### Required action

1. Phase A scope should be: add `loss_type` field to `DPOConfig.to_trl_config()` passthrough. Do NOT expand the `method` enum yet.
2. Phase B should expand the `method` enum simultaneously with implementing the handlers
3. Or: Phase A includes a stub-free fallback that raises `TrainingError("Method 'grpo' requires kailash-align >= X.Y.Z with online RL support")` with a clear message, not a generic "unknown method" error

---

## Finding M1: Missing Data Format — Chat/Conversational Template Support (MEDIUM)

### What the analysis covers

Four data formats are identified (document 12):

1. `{prompt, chosen, rejected}` — preference pairs
2. `{prompt, completion, label}` — binary feedback
3. `{prompt}` + reward function — online RL
4. `{prompt, chosen, rejected}` + online rollouts

### What is missing

**Chat-format / multi-turn conversational data** is not addressed. TRL 1.0+ requires datasets in either:

- **Standard format**: `{prompt, chosen, rejected}` with text strings
- **Conversational format**: `{prompt, chosen, rejected}` where each is a list of `{"role": "user"/"assistant", "content": "..."}`

The conversational format is critical for:

- Multi-turn dialogue alignment (ChatGPT, Claude-style)
- System prompt inclusion in training data
- Role-based formatting differences across model architectures (Llama uses `[INST]`, Mistral uses `<s>`, ChatML uses `<|im_start|>`)

TRL handles this via `tokenizer.apply_chat_template()`, but kailash-align's data validators would need to accept both formats and the pipeline would need to configure the tokenizer's chat template correctly.

Additionally, SFT data format is listed as `{text}` but TRL's SFTTrainer also accepts conversational format (`{messages}` with role/content dicts). The existing `SFTConfig.dataset_text_field = "text"` assumes the flat format only.

### Required action

1. Add conversational data format to the format inventory
2. Design data validators that accept both flat and conversational formats
3. Add `chat_template` parameter to config or auto-detect from tokenizer

---

## Finding M2: Multi-GPU / Distributed Training — Unaddressed (MEDIUM)

### What the analysis assumes

All five documents assume single-GPU training. No document mentions:

- `accelerate` multi-GPU configuration
- DeepSpeed ZeRO stages
- FSDP (Fully Sharded Data Parallel)
- Multi-node training

### Why this matters

The pyproject.toml already pins `accelerate>=1.4,<2.0`. Accelerate is the standard library for distributed training with HuggingFace. But the AlignmentPipeline has no `accelerate` configuration surface:

- No `num_processes` parameter
- No DeepSpeed config path
- No FSDP sharding strategy
- No `gradient_checkpointing` interaction with DeepSpeed (they conflict in certain configurations)

For models larger than 7B:

- 13B with QLoRA: fits on single A100 80GB (barely)
- 13B with full LoRA: requires 2x A100 or DeepSpeed ZeRO-3
- 34B+: always requires multi-GPU

GRPO exacerbates this because `num_generations` multiplies the memory requirement. A 7B GRPO run with `num_generations=16` may require 2-4 GPUs even with vLLM offloading.

### Required action

1. Add `accelerate_config_path: Optional[str]` to AlignmentConfig for advanced users
2. Document single-GPU vs. multi-GPU feasibility per method and model size
3. At minimum, detect `torch.cuda.device_count()` and warn if the configuration likely exceeds single-GPU memory

---

## Finding M3: Effort Estimates Use Human-Days, Violating Autonomous Execution Rules (MEDIUM)

### What the analysis states

Document 10 (Section 7) provides effort estimates in human-days:

| Task                      | Effort      |
| ------------------------- | ----------- |
| Method registry + factory | 2 days      |
| Generic trainer wrapper   | 2 days      |
| ...                       | ...         |
| **Total**                 | **17 days** |

### What is wrong

Per `rules/autonomous-execution.md`:

> agents MUST NOT estimate effort in "human-days" or "developer-weeks"

> agents MUST estimate effort in **autonomous execution cycles** (sessions, not days)

The synthesis (document 12) correctly uses "sessions" as the unit in its phasing, but the implementation audit uses "days." This inconsistency could confuse planning.

By the autonomous execution model:

- "17 human-days" = approximately 2-3 autonomous sessions (the 10x multiplier applies since COC institutional knowledge for kailash-align is already well-populated across 11 research documents)

### Required action

1. Replace human-day estimates in document 10 with autonomous session estimates
2. Align with document 12's session-based phasing

---

## Finding M4: Classical RL Boundary — GRPO in Classical RL Environments Is Unexplored (MEDIUM)

### What the analysis states

Document 09 (Section 4.3) and document 08 (Section 3.2) draw a firm boundary:

> "GRPO/RLHF stays in kailash-align. This is not debatable."

> "Rule: If the policy is a language model and the 'environment' is text generation, it belongs in kailash-align."

### What is partially wrong

Document 08 mentions in passing (Section 3.2):

> "Recent research (arXiv:2511.03527) explores GRPO in classical RL but finds PPO's critic still valuable in stochastic environments."

This is acknowledged but dismissed. However, the boundary is not as clean as stated:

1. **GRPO for tool-use agents**: Kaizen agents that use tools in gymnasium-like environments (web browsing, file system interaction) blur the line. The "environment" is a tool execution context, the "policy" is an LLM, and the "reward" is task completion. This is neither pure LLM alignment nor pure classical RL.

2. **The emerging "LLM agent RL" category**: Papers like WebArena-GRPO and SWE-agent-RL train LLMs to interact with environments using GRPO. The training infrastructure is TRL-based (kailash-align territory), but the evaluation is environment-based (kailash-ml[rl] territory).

3. **Reward model training for classical RL**: If classical RL environments use LLM-based reward shaping (using an LLM to evaluate state quality), the reward model training belongs in kailash-align even though the RL training belongs in kailash-ml[rl].

### Required action

1. Acknowledge the blurring boundary in the synthesis
2. Define a clear interface: kailash-align provides reward functions; kailash-ml[rl] provides environments. When both are involved, kailash-align drives training.
3. Do not change the primary recommendation, but document the edge cases

---

## Finding M5: Missing Method — RewardTrainer / Process Reward Models (MEDIUM)

### What the analysis covers

Document 08 lists `RewardTrainer` and `PRMTrainer` in the TRL trainer inventory. Document 12 mentions "RewardModelConfig + reward model training pipeline" as Phase 4 (v2.0, advanced).

### What is missing

The analysis underestimates the importance of reward model training for the online RL pipeline. GRPO can use either:

1. **Rule-based reward functions** (verifiable rewards) — no training needed
2. **Trained reward models** (learned preferences) — requires RewardTrainer

The synthesis puts reward model training in Phase 4, but GRPO with learned reward models is a Phase C concern. If Phase C implements GRPO without reward model training, users are limited to rule-based rewards only. This is fine for math/coding (RLVR), but not for general alignment where correctness is not programmatically verifiable.

Additionally, **Process Reward Models (PRM)** are distinct from Outcome Reward Models (ORM). PRMs score each intermediate reasoning step, not just the final answer. TRL has `PRMTrainer` for this. PRMs are essential for chain-of-thought reasoning (the DeepSeek-R1 use case). The analysis does not mention PRMs at all beyond listing the trainer name.

### Required action

1. Move basic RewardTrainer integration into Phase C (alongside GRPO), not Phase 4
2. Add PRMTrainer to the method inventory with proper description
3. Clarify: Phase C should support both rule-based and trained reward functions for GRPO

---

## Finding L1: kailash-rs Gap Analysis Overstates "Feature Parity" Requirement (LOW)

### What the analysis claims

Document 11 states:

> "The Kailash philosophy is **feature parity across languages**."

### What is questionable

This is stated as a fact but is not substantiated by any cited policy. The cross-SDK inspection rules (`rules/cross-sdk-inspection.md`) require inspecting the other SDK when an issue is found, and EATP D6 requires "matching semantics" — but neither mandates feature parity for training workloads.

Training is inherently a Python activity (PyTorch, TRL, HuggingFace ecosystem are Python-only). The Rust SDK's value is in inference and serving. Describing the absence of Rust training as a "CRITICAL GAP" may misdirect effort. The recommended path (Rust handles serving, Python handles training) is correct, but framing it as a gap implies it needs to be closed.

### Required action

1. Reframe as "cross-SDK integration point" rather than "critical gap"
2. The Rust crate recommendation (kailash-align-serving) is sound; just adjust the severity framing

---

## Summary

| ID  | Severity | Finding                                                                                    | Status |
| --- | -------- | ------------------------------------------------------------------------------------------ | ------ |
| C1  | CRITICAL | TRL version claims are incorrect; phantom trainers listed; version pin excludes stable API | Open   |
| C2  | CRITICAL | Reward function security (code injection via callable) not addressed                       | Open   |
| C3  | HIGH     | GPU memory analysis missing for online methods; vLLM memory split unaddressed              | Open   |
| C4  | HIGH     | vLLM as inference backend completely absent from MethodRegistry and dependency design      | Open   |
| H1  | HIGH     | MethodRegistry eager imports break lazy import pattern                                     | Open   |
| H2  | HIGH     | ORPO data format claim is incorrect (phantom `margin` column)                              | Open   |
| H3  | HIGH     | Phase A expands validation without implementation, creating validation-implementation gap  | Open   |
| M1  | MEDIUM   | Chat/conversational data format missing from inventory                                     | Open   |
| M2  | MEDIUM   | Multi-GPU / distributed training not addressed                                             | Open   |
| M3  | MEDIUM   | Effort estimates use human-days, violating autonomous execution rules                      | Open   |
| M4  | MEDIUM   | GRPO boundary between kailash-align and kailash-ml[rl] is blurrier than stated             | Open   |
| M5  | MEDIUM   | RewardTrainer/PRMTrainer phasing is too late for GRPO usability                            | Open   |
| L1  | LOW      | kailash-rs "feature parity" overstated for training workloads                              | Open   |

**Critical findings**: 2
**High findings**: 5
**Medium findings**: 5
**Low findings**: 1
**Total**: 13

---

## Convergence Criteria

This red team round is NOT converged. The 2 CRITICAL and 5 HIGH findings must be resolved before implementation begins. Specifically:

1. **C1** requires verified TRL API documentation check (web search recommended)
2. **C2** requires a security design decision on reward function specification
3. **C3 + C4** require a GPU memory analysis and vLLM integration design
4. **H1** requires MethodRegistry redesign (lazy imports)
5. **H2** requires data format correction (remove phantom column)
6. **H3** requires phasing adjustment (do not expand method enum before handlers exist)

A convergence round (R2) should verify all CRITICAL and HIGH findings are addressed before proceeding to `/todos`.
