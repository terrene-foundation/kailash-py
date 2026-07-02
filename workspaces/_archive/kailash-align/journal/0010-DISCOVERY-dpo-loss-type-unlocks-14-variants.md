---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T13:45:00+08:00
author: agent
session_turn: 45
project: kailash-align
topic: DPO loss_type parameter unlocks 14 alignment variants with zero code change
phase: analyze
tags: [alignment, dpo, trl, quick-win, architecture]
---

# DPO loss_type Unlocks 14 Variants

## Finding

TRL's `DPOTrainer` supports a `loss_type` parameter that switches between 14+ preference optimization objectives without changing the trainer class. kailash-align currently hardcodes `loss_type="sigmoid"` (standard DPO) and ignores this parameter entirely.

Available loss types: `sigmoid` (DPO), `hinge`, `ipo`, `exo_pair`, `nca_pair`, `robust`, `bco_pair`, `sppo_hard`, `aot`, `aot_pair`, `apo_zero`, `apo_down`, `simpo`, `cpo`, `padll`.

This means IPO, SimPO, NCA, CPO, BCO, and 9 other methods are available TODAY through a single config field addition — no new trainer code, no new data formats, no new pipeline logic.

## Impact

- **Immediate**: Adding `loss_type: str = "sigmoid"` to AlignmentConfig and passing it through to TRL's DPOConfig unlocks 14 preference optimization variants
- **Effort**: ~30 minutes of code changes + tests
- **Value**: Covers the entire offline preference optimization landscape without architectural changes

## What This Does NOT Cover

- KTO (needs KTOTrainer, different data format: unpaired binary labels)
- ORPO (needs ORPOTrainer, different loss formulation)
- GRPO, RLOO (online RL methods, need rollout pipeline)
- These require the full MethodRegistry refactor

## For Discussion

1. Should we expose all 14 loss types or curate a recommended subset? Some (like `aot_pair`, `padll`) are experimental and may confuse users.
2. If SimPO and IPO are available as DPO `loss_type` variants, does a user ever need to think about them as separate "methods"? Or should kailash-align present them as "DPO with optimization X"?
3. What happens when TRL changes loss_type names between versions? Should we validate against a known-good list or pass through?
