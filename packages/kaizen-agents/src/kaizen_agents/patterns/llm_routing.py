# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""LLM-based routing strategy for multi-agent orchestration.

Wraps the existing ``llm_capability_match`` and ``llm_text_similarity``
functions from ``kaizen.llm.reasoning`` in a callable strategy object
compatible with the orchestration runtime.

This class satisfies the spec requirement (HIGH 10.3) for an ``LLMBased``
routing strategy that uses Kaizen signatures to score agent capabilities
against task requirements.  The underlying LLM reasoning is fully
implemented in ``kaizen.llm.reasoning``; this module provides the
strategy-shaped interface that ``OrchestrationRuntime`` and wrapper
agents consume.

Usage::

    from kaizen_agents.patterns.llm_routing import LLMBased

    strategy = LLMBased()
    score = await strategy.score("translate this document", capability)
    best = await strategy.select_best("translate this doc", candidates)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from kaizen.core.base_agent import BaseAgentConfig
from kaizen.llm.reasoning import llm_capability_match, llm_text_similarity

logger = logging.getLogger(__name__)

__all__ = [
    "LLMBased",
]


class LLMBased:
    """LLM-based routing strategy that uses Kaizen signatures to score
    agent capabilities against task requirements.

    Wraps the existing ``llm_capability_match`` and ``llm_text_similarity``
    functions in a callable strategy object compatible with the
    orchestration runtime.

    Parameters
    ----------
    config:
        Optional ``BaseAgentConfig`` for model selection.  When ``None``,
        the underlying reasoning helpers fall back to ``.env``-defined
        defaults per ``rules/env-models.md``.
    """

    def __init__(self, config: Optional[BaseAgentConfig] = None) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def score(
        self,
        task: str,
        capability: Any,
        *,
        correlation_id: Optional[str] = None,
    ) -> float:
        """Score how well *capability* matches *task* via the LLM.

        *capability* may be:

        - A ``Capability`` dataclass (has ``.name`` and ``.description``)
          -- delegates to ``llm_capability_match``.
        - A plain string -- delegates to ``llm_text_similarity``.

        Returns a float in ``[0.0, 1.0]``.
        """
        cid = correlation_id or f"llmbased_{uuid.uuid4().hex[:8]}"
        return self._score_one(task, capability, cid)

    async def select_best(
        self,
        task: str,
        candidates: list[Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Any:
        """Score all *candidates* against *task* and return the highest.

        Each candidate may be a ``Capability`` dataclass, a plain string,
        or any object with ``.name`` and ``.description`` attributes.

        Returns ``None`` when *candidates* is empty.
        """
        if not candidates:
            return None

        cid = correlation_id or f"llmbased_{uuid.uuid4().hex[:8]}"

        best_candidate: Any = None
        best_score: float = -1.0

        for candidate in candidates:
            s = self._score_one(task, candidate, cid)
            if s > best_score:
                best_score = s
                best_candidate = candidate

        logger.info(
            "llm_routing.select_best.ok",
            extra={
                "correlation_id": cid,
                "num_candidates": len(candidates),
                "best_score": best_score,
            },
        )
        return best_candidate

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _score_one(
        self,
        task: str,
        capability: Any,
        correlation_id: str,
    ) -> float:
        """Score a single capability against a task.

        Delegates to the appropriate reasoning helper based on the
        capability's type.
        """
        cap_name = getattr(capability, "name", None)
        cap_desc = getattr(capability, "description", None)

        if cap_name is not None:
            # Structured capability with name (and optional description)
            return llm_capability_match(
                capability_name=cap_name,
                capability_description=cap_desc or cap_name,
                requirement=task,
                config=self._config,
                correlation_id=correlation_id,
            )

        # Fall back to text similarity for plain strings
        cap_text = str(capability) if not isinstance(capability, str) else capability
        return llm_text_similarity(
            text_a=task,
            text_b=cap_text,
            config=self._config,
            correlation_id=correlation_id,
        )
