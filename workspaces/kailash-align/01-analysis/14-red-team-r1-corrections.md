# Red Team R1 Corrections

Applied corrections based on 13 findings from red team report (13-red-team-r1.md).

## C1: TRL Version — ACCEPTED

- IPOTrainer and SimPOTrainer do NOT exist as standalone classes. They are `loss_type` on DPOTrainer.
- Current pin `trl>=0.25,<1.0` excludes TRL 1.0 where GRPO/RLOO became stable.
- **Action**: Bump to `trl>=1.0,<2.0` for stable GRPO/RLOO API. Remove phantom trainer references from doc 10.

## C2: Reward Function Security — ACCEPTED

- GRPO/RLOO accept arbitrary callables as reward functions. No security model defined.
- **Action**: Reward functions MUST be Python objects passed programmatically. NO serialization (pickle), NO string-based dynamic import, NO eval. Named reward functions via a `RewardRegistry` pattern (register by name, look up by name). Config files reference names, not code.

## C3: GPU Memory — ACCEPTED

- "50% savings" claims are misleading without concrete memory analysis.
- GRPO with num_generations=16 on 7B exceeds single A100 80GB.
- **Action**: Add GPU memory table to architecture. Default `num_generations=4` (not 16). Document vLLM memory partitioning.

## C4: vLLM Missing — ACCEPTED

- vLLM is essential for production GRPO but absent from architecture, MethodConfig, and dependencies.
- **Action**: Add `[online]` extra with `vllm>=0.6`. Add `supports_vllm` and `requires_generation_backend` to MethodConfig. Handle vLLM lifecycle in online pipeline.

## H1: Lazy Imports — ACCEPTED

- Module-level `type` references in MethodRegistry break lazy imports.
- **Action**: Use string-based references (`trainer_module: str`, `trainer_class_name: str`) with `importlib.import_module()` at training time.

## H2: ORPO Data Format — ACCEPTED

- ORPO uses standard `{prompt, chosen, rejected}`, not a phantom `margin` column.
- **Action**: Remove incorrect column claim from doc 10.

## H3: Phase A Validation Gap — ACCEPTED

- Expanding method enum without implementing handlers creates crash-on-train.
- **Action**: Phase A must pair validation expansion with at least a pass-through to TRL (lazy import + generic wrapper). Never validate a method that can't train.

## M1-M5: All ACCEPTED

- M1: Add chat/multi-turn data format to inventory
- M2: Document DeepSpeed/FSDP integration via `accelerate`
- M3: Remove human-day estimates from doc 10 (use autonomous sessions)
- M4: Acknowledge GRPO boundary is blurry for tool-use agents (edge case, document it)
- M5: Move RewardTrainer to Phase B (needed for non-verifiable GRPO use cases)

## Status

All 13 findings accepted. No findings rejected. Corrections applied to synthesis and architecture for /todos phase.
