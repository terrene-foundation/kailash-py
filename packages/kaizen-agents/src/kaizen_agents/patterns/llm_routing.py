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
from typing import Any

from kaizen.core.base_agent import BaseAgentConfig
from kaizen.llm.reasoning import (
    ReasoningDegradedError,
    llm_capability_match,
    llm_text_similarity,
)

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

    def __init__(self, config: BaseAgentConfig | None = None) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def score(
        self,
        task: str,
        capability: Any,
        *,
        correlation_id: str | None = None,
    ) -> float:
        """Score how well *capability* matches *task* via the LLM.

        *capability* may be:

        - A ``Capability`` dataclass (has ``.name`` and ``.description``)
          -- delegates to ``llm_capability_match``.
        - A plain string -- delegates to ``llm_text_similarity``.

        Returns a float in ``[0.0, 1.0]``.

        Raises:
            ReasoningDegradedError: The LLM judge returned without a usable
                score (#1981). This is a single-capability query with no
                ranking round to sink, so there is nothing to fall back to:
                any float returned here would be a fabricated answer the
                caller cannot distinguish from a genuine no-match. The
                ORIGINAL error is re-raised (it carries the model,
                correlation ID and the model's raw response) after a WARN
                line makes the degradation triageable at this layer.
        """
        cid = correlation_id or f"llmbased_{uuid.uuid4().hex[:8]}"
        try:
            return self._score_one(task, capability, cid)
        except ReasoningDegradedError as exc:
            logger.warning(
                "llm_routing.score.degraded",
                extra={
                    "correlation_id": cid,
                    "helper": exc.helper,
                    "model": exc.model,
                    "error": exc.error,
                },
            )
            raise

    async def select_best(
        self,
        task: str,
        candidates: list[Any],
        *,
        correlation_id: str | None = None,
    ) -> Any:
        """Score all *candidates* against *task* and return the highest.

        Each candidate may be a ``Capability`` dataclass, a plain string,
        or any object with ``.name`` and ``.description`` attributes.

        Returns ``None`` when *candidates* is empty.

        Degraded judgments (#1981): a candidate the LLM judge could not
        score is EXCLUDED from the ranking and logged at WARN, never ranked
        at ``0.0`` -- a fabricated zero is indistinguishable from a genuine
        no-match, so one degraded candidate could out-rank a real one and
        the "best" pick would be decided by iteration order rather than fit.
        Mirrors ``A2ACoordinatorNode._find_best_agents_for_task``.

        Raises:
            ReasoningDegradedError: EVERY candidate degraded, so no ranking
                exists. Returning any candidate here would be an arbitrary
                pick presented as a judged one.
        """
        if not candidates:
            return None

        cid = correlation_id or f"llmbased_{uuid.uuid4().hex[:8]}"

        best_candidate: Any = None
        best_score: float = -1.0
        scored = 0
        degraded: list[str] = []
        degraded_model = "unknown"

        for index, candidate in enumerate(candidates):
            try:
                s = self._score_one(task, candidate, cid)
            except ReasoningDegradedError as exc:
                # This candidate's fit is UNKNOWN, not zero. Ranking it at
                # 0.0 is exactly what made the selection arbitrary in #1981.
                degraded.append(getattr(candidate, "name", None) or str(candidate))
                degraded_model = exc.model
                logger.warning(
                    "llm_routing.select_best.candidate_degraded",
                    extra={
                        "correlation_id": cid,
                        "candidate_index": index,
                        "helper": exc.helper,
                        "model": exc.model,
                        "error": exc.error,
                    },
                )
                continue

            scored += 1
            if s > best_score:
                best_score = s
                best_candidate = candidate

        if degraded:
            if scored == 0:
                # Nothing was scoreable: there is no ranking to return, and
                # any candidate handed back would be read by the caller as a
                # judged best-fit.
                raise ReasoningDegradedError(
                    "llm_routing.select_best",
                    model=degraded_model,
                    correlation_id=cid,
                    error=(
                        f"the LLM judge degraded for all {len(candidates)} "
                        f"candidate(s): {', '.join(degraded)}"
                    ),
                )
            logger.warning(
                "llm_routing.select_best.degraded",
                extra={
                    "correlation_id": cid,
                    "num_candidates": len(candidates),
                    "ranked": scored,
                    "degraded_candidates": degraded,
                },
            )

        logger.info(
            "llm_routing.select_best.ok",
            extra={
                "correlation_id": cid,
                "num_candidates": len(candidates),
                "ranked": scored,
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

        Raises:
            ReasoningDegradedError: Propagated from the reasoning helper when
                the judge returned no usable score (#1981). Every caller of
                this method handles it explicitly -- it MUST NOT be coerced
                back to a float here.
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
