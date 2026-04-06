# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Alignment workflow orchestrator — composes 4 agents in pipeline order.

This is a stateless convenience function, not a requirement.  Users can
call agents individually.  The orchestrator composes:
    Strategist → DataCuration → TrainingConfig → (train) → EvalInterpreter
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["alignment_workflow"]


async def alignment_workflow(
    base_model_info: str,
    dataset_summary: str,
    gpu_memory: str,
    dataset_size: str,
    *,
    constraints: str = "",
    available_methods: str = "",
    preference_quality: str = "",
    eval_results: Optional[str] = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the full alignment advisory pipeline.

    Composes: Strategist → DataCuration → TrainingConfig.
    If ``eval_results`` is provided, also runs EvalInterpreter.

    Args:
        base_model_info: Model metadata string.
        dataset_summary: Dataset statistics string.
        gpu_memory: GPU information string.
        dataset_size: Dataset size string.
        constraints: Optional constraints string.
        available_methods: Optional methods list string.
        preference_quality: Optional preference quality metrics.
        eval_results: Optional eval results (triggers interpretation step).
        model: LLM model override for all agents.

    Returns:
        Dict with strategy, curation, config, and optionally interpretation.
    """
    from kailash_align.agents.strategist import AlignmentStrategistAgent
    from kailash_align.agents.data_curation import DataCurationAgent
    from kailash_align.agents.training_config import TrainingConfigAgent

    # Step 1: Strategy
    strategist = AlignmentStrategistAgent(model=model)
    strategy = await strategist.recommend(
        base_model_info=base_model_info,
        dataset_summary=dataset_summary,
        constraints=constraints,
        available_methods=available_methods,
    )
    logger.info(
        "Strategist recommended: %s (confidence: %s)",
        strategy.get("method_recommendation", "unknown"),
        strategy.get("confidence", "N/A"),
    )

    # Step 2: Data curation
    curator = DataCurationAgent(model=model)
    curation = await curator.evaluate(
        dataset_stats=dataset_summary,
        preference_quality=preference_quality,
        training_method=strategy.get("method_recommendation", ""),
    )

    # Step 3: Training config
    configurator = TrainingConfigAgent(model=model)
    config = await configurator.configure(
        training_method=strategy.get("method_recommendation", ""),
        model_info=base_model_info,
        gpu_memory=gpu_memory,
        dataset_size=dataset_size,
    )

    result: dict[str, Any] = {
        "strategy": strategy,
        "curation": curation,
        "config": config,
    }

    # Step 4 (optional): Eval interpretation
    if eval_results is not None:
        from kailash_align.agents.eval_interpreter import EvalInterpreterAgent

        interpreter = EvalInterpreterAgent(model=model)
        interpretation = await interpreter.interpret(
            eval_results=eval_results,
            training_config=str(config),
        )
        result["interpretation"] = interpretation

    return result
