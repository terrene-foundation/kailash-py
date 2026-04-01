# TRL Ecosystem Analysis

## 1. TRL's Current API Surface (v0.29+, March 2026)

### SFTTrainer

TRL's `SFTTrainer` extends HuggingFace `transformers.Trainer` with SFT-specific features:

```python
from trl import SFTTrainer, SFTConfig

sft_config = SFTConfig(
    output_dir="./sft_output",
    max_seq_length=2048,
    gradient_checkpointing=True,
    bf16=True,
    per_device_train_batch_size=4,
    num_train_epochs=3,
    learning_rate=2e-4,
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=sft_config,
)
trainer.train()
```

Key features TRL handles natively:

- Automatic tokenizer padding/truncation configuration
- Chat template formatting for instruction datasets
- Dataset column auto-detection ("text" column or chat format)
- Packing (multiple short sequences in one training sample)
- PEFT/LoRA integration via `peft_config` parameter
- Gradient checkpointing configuration
- Mixed precision (bf16/fp16) via HF Trainer args

### DPOTrainer

TRL's `DPOTrainer` implements Direct Preference Optimization:

```python
from trl import DPOTrainer, DPOConfig

dpo_config = DPOConfig(
    output_dir="./dpo_output",
    beta=0.1,  # DPO temperature
    bf16=True,
    gradient_checkpointing=True,
)

trainer = DPOTrainer(
    model=model,
    ref_model=None,  # None = implicit reference (no extra GPU memory)
    tokenizer=tokenizer,
    train_dataset=preference_dataset,
    args=dpo_config,
)
trainer.train()
```

Key features:

- Implicit reference model support (`ref_model=None` uses the SFT model as reference)
- Preference data format: `{"prompt": ..., "chosen": ..., "rejected": ...}`
- Multiple DPO variants: IPO, KTO, CPO, ORPO (all via config flags)
- PEFT integration for memory-efficient training

### What TRL Already Provides (That AlignmentPipeline Would Wrap)

| Feature                | TRL Native?                         | AlignmentPipeline Adds       |
| ---------------------- | ----------------------------------- | ---------------------------- |
| SFT training           | Yes                                 | Nothing -- pure pass-through |
| DPO training           | Yes                                 | Nothing -- pure pass-through |
| LoRA/QLoRA             | Yes (via `peft_config` param)       | Nothing -- pure pass-through |
| Gradient checkpointing | Yes                                 | Nothing                      |
| Mixed precision        | Yes                                 | Nothing                      |
| Multi-GPU (Accelerate) | Yes                                 | Nothing                      |
| Checkpoint saving      | Yes (HF Trainer built-in)           | Nothing                      |
| Checkpoint resuming    | Yes (`resume_from_checkpoint=True`) | Nothing                      |
| Dataset formatting     | Yes (chat templates)                | Nothing                      |

## 2. What AlignmentPipeline Actually Wraps vs. What TRL Provides

### Honest Assessment

Looking at the architecture doc's `_run_sft()` and `_run_dpo()` methods:

```python
# This is essentially:
trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=dataset, args=sft_args)
trainer.train()
trainer.save_model(str(checkpoint_dir / "sft_final"))
```

That is 3 lines. AlignmentPipeline does NOT add training logic -- it is a **thin orchestrator** over TRL trainers. The actual value is elsewhere.

### Where AlignmentPipeline Adds Genuine Value

1. **SFT-then-DPO sequencing**: Coordinating two training phases in order, managing the model state between them, and handling the adapter checkpoint handoff. Without AlignmentPipeline, users write a script that does this manually. This is real but small value.

2. **AdapterRegistry integration**: After training, the adapter is automatically registered with metadata (base model, LoRA config, training metrics, experiment ID). This is the primary value -- it connects training output to the rest of the pipeline (evaluation, serving, Kaizen).

3. **Air-gapped model loading**: The `_load_base_model()` method handles `local_files_only` propagation, QLoRA quantization config, and offline cache resolution. Without this, users must handle these flags manually.

4. **Experiment tracking**: `AlignExperiment` DataFlow model stores the full training context. Without this, users keep their own spreadsheets.

### What AlignmentPipeline Does NOT Add

- No novel training algorithms
- No custom loss functions
- No training loop modifications
- No data preprocessing beyond what TRL handles
- No hyperparameter optimization
- No distributed training coordination (Accelerate handles this)

## 3. PEFT/LoRA Integration State (2026)

### Current State

PEFT (Parameter-Efficient Fine-Tuning) is mature and well-integrated with TRL:

```python
from peft import LoraConfig

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.1,
    bias="none",
    task_type="CAUSAL_LM",
)

# TRL accepts LoraConfig directly
trainer = SFTTrainer(
    model=model,
    peft_config=lora_config,  # PEFT integration is native
    ...
)
```

Key points:

- PEFT v0.14+ (March 2026) is stable
- LoRA target module auto-detection is reliable for major architectures (Llama, Mistral, Phi, Qwen)
- QLoRA (4-bit quantization) via bitsandbytes is the standard memory optimization
- Adapter merging via `PeftModel.merge_and_unload()` is stable and well-tested
- Adapter saving produces small files (50-500MB vs 8-30GB for full model)

### Risks

- **Target module selection**: Different model architectures use different module names. Auto-detection works for popular models but may fail for newer architectures.
- **QLoRA + gradient checkpointing**: Occasional compatibility issues between bitsandbytes, PEFT, and specific transformers versions. This is the most fragile dependency chain.
- **4-bit inference**: Models loaded in 4-bit for training cannot be directly served -- they must be merged and optionally re-quantized for serving.

## 4. Is the Framework Adding Value or Just Wrapping?

### Verdict: Thin Wrapper With Strategic Integration Value

AlignmentPipeline is a **thin wrapper** around TRL. The training code itself is 3-5 lines per phase. A user could write this in a Jupyter notebook in 20 minutes.

The genuine value is NOT in the training:

| Component                 | Value Source                                | Magnitude                                |
| ------------------------- | ------------------------------------------- | ---------------------------------------- |
| AlignmentPipeline.train() | Orchestration + AdapterRegistry integration | Low (could be a script)                  |
| AdapterRegistry           | Version management + metadata tracking      | **High** (no equivalent exists)          |
| AlignmentEvaluator        | Standardized evaluation + result storage    | Medium (wraps lm-eval)                   |
| AlignmentServing          | GGUF export + Ollama deployment             | **High** (manual process is error-prone) |
| KaizenModelBridge         | Delegate auto-configuration                 | Medium (convenience)                     |

**The framework's value is in the lifecycle management (registry, evaluation, serving, Kaizen integration), not in the training itself.** If the framework only did training, it would not justify its existence. The training is the thinnest layer; everything around it is where kailash-align earns its keep.

## 5. Ecosystem Velocity Risk

TRL moves fast. Between v0.8 (architecture doc's minimum) and v0.29 (current):

- `SFTTrainer` was renamed from `SFTTrainer` (stable) but `SFTConfig` replaced `TrainingArguments` for SFT-specific config
- `DPOConfig` replaced passing `TrainingArguments` to `DPOTrainer`
- New trainers added: `GRPOTrainer`, `OnlineDPOTrainer`, `KTOTrainer`
- Internal restructuring of data collators and formatting

**Risk**: kailash-align pinning `trl>=0.8` is too loose. The API changed significantly between 0.8 and 0.29. Should pin to a narrower range (e.g., `trl>=0.25,<1.0`) and test against specific versions.

**Mitigation**: AlignmentPipeline's TRL surface area is small (SFTTrainer + DPOTrainer + their Config classes). Breaking changes in other TRL components (GRPO, KTO, reward modeling) do not affect kailash-align.
