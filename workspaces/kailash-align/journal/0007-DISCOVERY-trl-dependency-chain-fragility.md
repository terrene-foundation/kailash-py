---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T14:30:00+08:00
author: agent
session_turn: 3
project: kailash-align
topic: The 5-level dependency chain torch-transformers-trl-peft-accelerate has specific known fragilities
phase: analyze
tags:
  [trl, peft, transformers, torch, version-pinning, dependency-management, risk]
---

# Five-Level Dependency Chain Has Specific Known Fragilities

## Discovery

Red team analysis of kailash-align's dependency stack reveals that the chain `torch -> transformers -> trl -> peft -> accelerate` is not just "large" -- it has specific, documented fragility points where version mismatches produce silent failures or breaking API changes.

### Fragility 1: TRL API Breakage (Concrete)

The architecture doc pins `trl>=0.8`, but the API changed substantially between 0.8 and 0.29 (current, March 2026):

- `SFTConfig` and `DPOConfig` replaced `TrainingArguments` for SFT/DPO-specific config
- Data collators were restructured internally
- New trainers were added (GRPOTrainer, OnlineDPOTrainer, KTOTrainer) with naming that could collide

A user installing kailash-align today with `trl>=0.8` could get TRL 0.12 (which lacks SFTConfig entirely), and AlignmentPipeline would fail at import time with an obscure ImportError. The fix is tightening to `trl>=0.25,<1.0`.

### Fragility 2: PEFT Adapter Portability (Subtle)

PEFT adapters saved with one version of transformers may not load correctly with a different version. The adapter files include model configuration snapshots that reference transformer class names and field layouts. When transformers reorganizes internal class hierarchies (which happens in minor releases), adapter loading can fail with `KeyError` or produce silently wrong weight mappings.

This directly affects AdapterRegistry: adapters versioned and stored via the registry may become unloadable if the user upgrades transformers between training and evaluation/serving.

### Fragility 3: QLoRA Silent Numerical Errors (Dangerous)

The combination of bitsandbytes (4-bit quantization) + gradient checkpointing + specific transformers versions has been observed to produce silent numerical issues where training appears to converge but the resulting adapter produces degraded output. This is architecture-specific (more common on consumer GPUs) and version-specific.

### Fragility 4: lm-eval Breaking Changes

lm-eval-harness has changed task definitions, metric names, and API signatures between minor versions. Evaluation results stored in DataFlow from one lm-eval version may use metric keys (e.g., `acc,none` vs `accuracy`) that do not match results from a later version, breaking comparison queries.

## Implications

1. Version pinning is not optional -- it is a correctness requirement. Loose pins (`>=0.8`) are functionally bugs.
2. A CI version matrix testing minimum and maximum of each pinned range is essential, not nice-to-have.
3. AdapterRegistry should store the versions of transformers, peft, and trl used during training as adapter metadata. This enables compatibility warnings at load time.
4. AlignmentEvaluator should store the lm-eval version alongside evaluation results to prevent cross-version metric comparison.

## Recommended Version Pins

| Package      | Current (Architecture Doc) | Recommended | Reason                                      |
| ------------ | -------------------------- | ----------- | ------------------------------------------- |
| torch        | >=2.2                      | >=2.2,<3.0  | Major version breaks everything             |
| transformers | >=4.40                     | >=4.40,<5.0 | Internal class hierarchy changes            |
| trl          | >=0.8                      | >=0.25,<1.0 | SFTConfig/DPOConfig API introduced in ~0.25 |
| peft         | >=0.10                     | >=0.10,<1.0 | Relatively stable but pre-1.0               |
| accelerate   | >=0.28                     | >=0.28,<1.0 | Required by TRL                             |
| lm-eval      | >=0.4                      | >=0.4,<1.0  | Task definition changes                     |
| bitsandbytes | >=0.43                     | >=0.43,<1.0 | QLoRA compatibility                         |

## For Discussion

1. The TRL version pin `>=0.8` in the architecture doc would allow installing a TRL version where `SFTConfig` does not exist, causing AlignmentPipeline to fail at import. Should the analysis phase produce a concrete `pyproject.toml` dependency spec rather than leaving version pins to implementation?
2. If AdapterRegistry stores the transformers version used during training, should it refuse to load an adapter trained with a different transformers major version, or just warn? A hard refusal protects against silent weight corruption but blocks legitimate cross-version use.
3. The QLoRA + gradient checkpointing numerical issue is architecture-specific (consumer GPUs more affected than datacenter GPUs). Should kailash-align detect the GPU architecture at training time and warn if the combination is known to be fragile?
