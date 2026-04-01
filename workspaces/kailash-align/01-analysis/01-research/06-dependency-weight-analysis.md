# Dependency Weight Analysis

## 1. Individual Package Sizes

### Core Dependencies (Required by kailash-align base install)

| Package                           | Install Size (approx.) | Notes                                             |
| --------------------------------- | ---------------------- | ------------------------------------------------- |
| torch                             | ~1.5-2.0 GB            | CPU-only. GPU builds (cu121, cu124) add 200-400MB |
| transformers                      | ~100-150 MB            | Pure Python + tokenizer binaries                  |
| trl                               | ~20-30 MB              | Pure Python, small footprint                      |
| peft                              | ~10-15 MB              | Pure Python                                       |
| accelerate                        | ~10-15 MB              | Pure Python                                       |
| datasets                          | ~40-60 MB              | Pure Python + Arrow bindings                      |
| lm-eval                           | ~30-50 MB              | Pure Python + task definitions                    |
| **Subtotal (kailash-align deps)** | **~1.7-2.3 GB**        |                                                   |

### Kailash Ecosystem Dependencies (Already installed)

| Package          | Install Size (approx.) | Notes                                   |
| ---------------- | ---------------------- | --------------------------------------- |
| kailash (core)   | ~5-10 MB               | Assumed pre-installed                   |
| kailash-dataflow | ~5-10 MB               | Required for AdapterRegistry storage    |
| kailash-kaizen   | ~5-10 MB               | Required for KaizenModelBridge          |
| kailash-ml       | ~195 MB                | Includes scikit-learn, LightGBM, polars |

### Optional Dependencies

| Package      | Install Size | Extra                  |
| ------------ | ------------ | ---------------------- |
| bitsandbytes | ~50-100 MB   | [rlhf] extra for QLoRA |

### Transitive Dependencies (Not Double-Counted)

torch pulls in: numpy, pillow, typing-extensions, sympy, networkx, jinja2, filelock, fsspec
transformers pulls in: tokenizers, safetensors, huggingface-hub, regex, requests, tqdm

These are typically already present in the environment if kailash-ml is installed (kailash-ml[dl] includes torch + transformers).

## 2. Total Install Size

### Scenario A: Clean Environment (No Kailash Pre-installed)

```
pip install kailash-align
```

Total: **~2.2-2.8 GB** (everything from scratch)

This is the worst case. In practice, nobody installs kailash-align without having kailash and at least some of the ecosystem.

### Scenario B: kailash-ml[dl] Already Installed

```
# kailash-ml[dl] already provides: torch, transformers, numpy, polars, scikit-learn, lightning
pip install kailash-align
```

Incremental: **~100-200 MB** (only trl, peft, accelerate, lm-eval, datasets)

This is the realistic scenario. Users who need LLM fine-tuning almost certainly already have torch + transformers installed via kailash-ml[dl] or directly.

### Scenario C: Only kailash-ml Base Installed (No [dl] Extra)

```
# kailash-ml base: scikit-learn, LightGBM, polars (no torch)
pip install kailash-align
```

Incremental: **~1.7-2.3 GB** (primarily torch + transformers)

## 3. Comparison to kailash-ml

| Package                                     | Base Install    | Notes                                         |
| ------------------------------------------- | --------------- | --------------------------------------------- |
| kailash-ml                                  | ~195 MB         | scikit-learn + LightGBM + polars              |
| kailash-ml[dl]                              | ~2.0-2.5 GB     | + torch + lightning + transformers            |
| kailash-align                               | ~2.2-2.8 GB     | + torch + transformers + trl + peft + lm-eval |
| **kailash-align incremental (from ml[dl])** | **~100-200 MB** | Only new packages                             |

The ~2.5 GB headline number is dominated by PyTorch (~1.5-2.0 GB). This is unavoidable for any package that does LLM work. Every LLM fine-tuning tool (Axolotl, Unsloth, LLaMA-Factory) has the same baseline.

## 4. Can Dependencies Be Made Optional?

### Assessment Per Dependency

| Dependency   | Make Optional?   | Impact                                                                     |
| ------------ | ---------------- | -------------------------------------------------------------------------- |
| torch        | No               | Core requirement for model loading, training, inference                    |
| transformers | No               | Core requirement for AutoModelForCausalLM, tokenizers                      |
| trl          | No               | Core requirement for SFTTrainer, DPOTrainer                                |
| peft         | No               | Core requirement for LoRA/QLoRA                                            |
| accelerate   | No               | Required by TRL for any training                                           |
| datasets     | Possible         | Only needed for HuggingFace dataset loading. Could use custom data loading |
| lm-eval      | **Yes**          | Only needed for AlignmentEvaluator                                         |
| bitsandbytes | Already optional | [rlhf] extra                                                               |

### Recommended Dependency Structure

```toml
[project]
dependencies = [
    "kailash>=1.0",
    "kailash-ml>=1.0",
    "kailash-kaizen>=1.0",
    "torch>=2.2",
    "transformers>=4.40",
    "trl>=0.25,<1.0",
    "peft>=0.10",
    "accelerate>=0.28",
    "datasets>=2.18",
]

[project.optional-dependencies]
eval = ["lm-eval>=0.4"]          # AlignmentEvaluator standard benchmarks
rlhf = ["bitsandbytes>=0.43"]    # QLoRA 4-bit quantization
serve = []                        # No Python deps; external binaries
full = ["kailash-align[eval,rlhf,serve]"]
```

Making lm-eval optional saves ~30-50 MB and avoids its transitive dependencies. Users who only train + deploy (no formal benchmarking) skip the eval overhead. AlignmentEvaluator would check for the import and raise a clear error:

```python
class AlignmentEvaluator:
    def __init__(self, ...):
        try:
            import lm_eval
        except ImportError as exc:
            raise ImportError(
                "AlignmentEvaluator requires the [eval] extra. "
                "Install with: pip install kailash-align[eval]"
            ) from exc
```

## 5. Is ~2.5 GB Acceptable?

### Perspective

- **LLM fine-tuning users expect large installs**: Anyone running `pip install torch` is already accepting 1.5-2 GB. Adding 500 MB for TRL/PEFT/lm-eval is marginal.
- **Comparison to alternatives**: Axolotl installs 3-4 GB. Unsloth installs 2-3 GB. LLaMA-Factory installs 2-3 GB. kailash-align at ~2.5 GB is typical.
- **The base model itself is 8-30 GB**: Users downloading Llama-3.2-8B (~16 GB) are not bothered by a 2.5 GB package install.
- **Separation from kailash-ml base**: The critical decision was making kailash-align a separate package. Users who only need tabular ML install kailash-ml (~195 MB). The 2.5 GB is isolated to users who explicitly choose LLM fine-tuning.

### Verdict

The ~2.5 GB install size is **acceptable and expected** for the target audience. It is not a dealbreaker. The package separation ensures it does not affect users who do not need LLM capabilities.

## 6. Dependency Version Pinning Recommendations

| Dependency   | Current Pin | Recommended Pin | Reason                                 |
| ------------ | ----------- | --------------- | -------------------------------------- |
| torch        | >=2.2       | >=2.2,<3.0      | Major version changes break everything |
| transformers | >=4.40      | >=4.40,<5.0     | Same                                   |
| trl          | >=0.8       | **>=0.25,<1.0** | API changed significantly since 0.8    |
| peft         | >=0.10      | >=0.10,<1.0     | Relatively stable API                  |
| accelerate   | >=0.28      | >=0.28,<1.0     | Relatively stable                      |
| datasets     | >=2.18      | >=2.18,<3.0     | Arrow format changes in major versions |
| lm-eval      | >=0.4       | >=0.4,<1.0      | API still evolving                     |

The most critical fix is tightening the TRL pin from `>=0.8` to `>=0.25,<1.0`. The API between 0.8 and 0.25 changed substantially (SFTConfig/DPOConfig classes introduced, data collator changes).
