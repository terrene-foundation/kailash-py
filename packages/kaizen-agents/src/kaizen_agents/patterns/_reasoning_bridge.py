"""
Sync/async bridge for LLM-first capability matching inside patterns.

Multi-agent patterns (`meta_controller`, `supervisor_worker`, `ensemble`,
`blackboard`) expose a synchronous `run()` contract — that is a public API
guarantee that pipeline callers rely on. Capability scoring, however, is
delegated to an async LLM reasoning helper (`Capability.matches_requirement`
is now `async def`). This module bridges the two so patterns stay sync on
the outside while the decision logic lives in the LLM.

Why a dedicated module:
    Without a shared bridge, each pattern file would re-implement the same
    loop/iscoroutine/asyncio.run dance, and any future capability-scoring
    change would need to touch four call sites. Centralising it here gives
    one place to add observability, caching, and fallbacks — aligned with
    `rules/agent-reasoning.md` MUST Rules 1 and 5.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from typing import Any

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.llm.reasoning import llm_text_similarity

logger = logging.getLogger(__name__)

__all__ = [
    "resolve_reasoning_config",
    "score_capability_sync",
    "score_capability_list_sync",
    "rank_agents_by_capability_sync",
]


def resolve_reasoning_config(
    agents: list[BaseAgent],
) -> BaseAgentConfig | None:
    """Return the first usable BaseAgentConfig from a list of agents.

    Picks the first agent that exposes a `.config` of type BaseAgentConfig
    so the reasoning judge shares the host agent's model. Returns None when
    no agent has a usable config; `llm_capability_match` then falls back to
    `.env`-defined defaults.
    """
    for agent in agents:
        candidate = getattr(agent, "config", None)
        if isinstance(candidate, BaseAgentConfig):
            return candidate
    return None


async def _score_capability_async(
    cap: Any,
    task: str,
    reasoning_config: BaseAgentConfig | None,
    *,
    correlation_id: str,
) -> float:
    """Single-capability async scoring helper.

    Accepts dataclass Capability (async matcher), legacy sync mocks, and
    plain strings. All error paths return 0.0 with a WARN log so one LLM
    failure cannot sink a whole selection round.
    """
    if isinstance(cap, str):
        try:
            return llm_text_similarity(
                text_a=task,
                text_b=cap,
                config=reasoning_config,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            logger.warning(
                "pattern.capability_score.similarity_failed",
                extra={"correlation_id": correlation_id, "error": str(exc)},
            )
            return 0.0

    matcher = getattr(cap, "matches_requirement", None)
    if matcher is None:
        return 0.0

    try:
        if inspect.iscoroutinefunction(matcher):
            return await matcher(
                task, config=reasoning_config, correlation_id=correlation_id
            )
        result = matcher(task)
        if inspect.iscoroutine(result):
            return await result
        return float(result)
    except TypeError:
        # Legacy sync mocks have a single positional parameter
        try:
            result = matcher(task)
            return float(result)
        except Exception as exc:
            logger.warning(
                "pattern.capability_score.legacy_match_failed",
                extra={"correlation_id": correlation_id, "error": str(exc)},
            )
            return 0.0
    except Exception as exc:
        logger.warning(
            "pattern.capability_score.match_failed",
            extra={"correlation_id": correlation_id, "error": str(exc)},
        )
        return 0.0


def _run_coroutine(coro) -> Any:
    """Execute an async coroutine from a sync context.

    Mirrors the `BaseAgent._run_async_hook` pattern: uses a threadpool when
    an event loop is already running (avoiding `asyncio.run` nesting
    errors), otherwise `asyncio.run` directly.
    """
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def score_capability_sync(
    cap: Any,
    task: str,
    *,
    reasoning_config: BaseAgentConfig | None = None,
    correlation_id: str | None = None,
) -> float:
    """Score a single capability against a task from a sync context."""
    cid = correlation_id or f"pattern_{uuid.uuid4().hex[:8]}"
    return _run_coroutine(
        _score_capability_async(cap, task, reasoning_config, correlation_id=cid)
    )


async def _score_capability_list_async(
    capabilities: list[Any],
    task: str,
    reasoning_config: BaseAgentConfig | None,
    correlation_id: str,
) -> float:
    """Return the best score across a list of capabilities for a task."""
    best_score = 0.0
    for cap in capabilities:
        score = await _score_capability_async(
            cap, task, reasoning_config, correlation_id=correlation_id
        )
        if score > best_score:
            best_score = score
    return best_score


def score_capability_list_sync(
    capabilities: list[Any],
    task: str,
    *,
    reasoning_config: BaseAgentConfig | None = None,
    correlation_id: str | None = None,
) -> float:
    """Return the max score across a capability list from a sync context."""
    cid = correlation_id or f"pattern_{uuid.uuid4().hex[:8]}"
    return _run_coroutine(
        _score_capability_list_async(capabilities, task, reasoning_config, cid)
    )


async def _rank_agents_async(
    agent_cards: list[tuple[Any, Any]],
    task: str,
    reasoning_config: BaseAgentConfig | None,
    correlation_id: str,
) -> list[tuple[Any, float]]:
    """Score every (agent, card) pair in one pass and return (agent, score)."""
    scored: list[tuple[Any, float]] = []
    for agent, card in agent_cards:
        capabilities = getattr(card, "primary_capabilities", None) or []
        score = await _score_capability_list_async(
            capabilities, task, reasoning_config, correlation_id
        )
        scored.append((agent, score))
    return scored


def rank_agents_by_capability_sync(
    agent_cards: list[tuple[Any, Any]],
    task: str,
    *,
    reasoning_config: BaseAgentConfig | None = None,
    correlation_id: str | None = None,
) -> list[tuple[Any, float]]:
    """Score (agent, card) pairs and return them unsorted with their scores.

    Patterns call this from their sync selection methods and then pick the
    best-scoring agent (or top-k). Sorting is left to the caller so each
    pattern can apply its own tie-breaking.
    """
    cid = correlation_id or f"pattern_{uuid.uuid4().hex[:8]}"
    return _run_coroutine(_rank_agents_async(agent_cards, task, reasoning_config, cid))
