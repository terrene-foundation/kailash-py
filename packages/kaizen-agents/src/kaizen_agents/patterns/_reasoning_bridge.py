"""
Sync/async bridge for LLM-first capability matching inside patterns.

Multi-agent patterns (`meta_controller`, `supervisor_worker`, `ensemble`,
`blackboard`) expose a synchronous `run()` contract — that is a public API
guarantee that pipeline callers rely on. Capability scoring is delegated to
an LLM reasoning helper, and a scorer may be EITHER sync (the built-in
`Capability.matches_requirement`, which awaits nothing — see #1973) or async
(third-party capability objects, custom matchers). This module bridges both
so patterns stay sync on the outside while the decision logic lives in the
LLM, and so the judge config reaches the matcher on either shape.

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
from kaizen.llm.reasoning import ReasoningDegradedError, llm_text_similarity

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

    Accepts dataclass Capability (sync matcher since #1973), async matchers,
    legacy sync mocks, and plain strings. INFRASTRUCTURE error paths return
    0.0 with a WARN log so one LLM failure cannot sink a whole selection
    round.

    Raises:
        ReasoningDegradedError: The judge returned without a usable score
            (#1981). This is deliberately NOT coerced to 0.0: a degraded
            judgment and a genuine no-match are the same float, so a caller
            ranking capabilities would tie them and pick by iteration order.
            The aggregating helpers above catch this PER CAPABILITY and skip
            the candidate, which is what preserves this module's documented
            "one LLM failure must not sink a round" intent -- the failure is
            now skipped rather than scored at a fabricated zero.
    """
    if isinstance(cap, str):
        try:
            return llm_text_similarity(
                text_a=task,
                text_b=cap,
                config=reasoning_config,
                correlation_id=correlation_id,
            )
        except ReasoningDegradedError as exc:
            logger.warning(
                "pattern.capability_score.similarity_degraded",
                extra={
                    "correlation_id": correlation_id,
                    "helper": exc.helper,
                    "model": exc.model,
                    "error": exc.error,
                },
            )
            raise
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
        # #1973: `Capability.matches_requirement` is sync (it awaits nothing),
        # so the judge config MUST be propagated on this branch too — otherwise
        # the judge silently falls back to `.env` defaults instead of the host
        # agent's model. Legacy single-arg mocks raise TypeError here and are
        # retried positionally by the handler below.
        result = matcher(task, config=reasoning_config, correlation_id=correlation_id)
        if inspect.iscoroutine(result):
            return await result
        return float(result)
    except ReasoningDegradedError as exc:
        # `Capability.matches_requirement` delegates to `llm_capability_match`,
        # so the typed degradation signal reaches this branch too. Ordered
        # BEFORE the generic handler so it cannot be flattened back to 0.0.
        logger.warning(
            "pattern.capability_score.match_degraded",
            extra={
                "correlation_id": correlation_id,
                "helper": exc.helper,
                "model": exc.model,
                "error": exc.error,
            },
        )
        raise
    except TypeError:
        # Legacy sync mocks have a single positional parameter
        try:
            result = matcher(task)
            return float(result)
        except ReasoningDegradedError as exc:
            logger.warning(
                "pattern.capability_score.legacy_match_degraded",
                extra={
                    "correlation_id": correlation_id,
                    "helper": exc.helper,
                    "model": exc.model,
                    "error": exc.error,
                },
            )
            raise
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
    """Score a single capability against a task from a sync context.

    Raises:
        ReasoningDegradedError: The judge returned no usable score (#1981).
            A single capability is not a ranking round -- there is no sibling
            candidate to fall back to, so any float returned here would be a
            fabricated answer indistinguishable from a genuine no-match.
    """
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
    """Return the best score across a list of capabilities for a task.

    Degraded capabilities (#1981) are SKIPPED, not scored at 0.0, so one
    unparseable judgment cannot sink an agent that has other capabilities the
    judge scored fine. An empty *capabilities* list is a genuine 0.0 (there
    was nothing to judge), not a degradation.

    Raises:
        ReasoningDegradedError: There was at least one capability and EVERY
            one degraded, so this agent's fit is UNKNOWN. Returning 0.0 here
            would be indistinguishable from "this agent matches nothing".
    """
    best_score = 0.0
    scored = 0
    degraded: list[str] = []
    degraded_model = "unknown"

    for cap in capabilities:
        try:
            score = await _score_capability_async(
                cap, task, reasoning_config, correlation_id=correlation_id
            )
        except ReasoningDegradedError as exc:
            degraded.append(getattr(cap, "name", None) or str(cap))
            degraded_model = exc.model
            continue

        scored += 1
        if score > best_score:
            best_score = score

    if degraded and scored == 0:
        raise ReasoningDegradedError(
            "pattern.score_capability_list",
            model=degraded_model,
            correlation_id=correlation_id,
            error=(
                f"the capability judge degraded for all {len(capabilities)} "
                f"capability/ies: {', '.join(degraded)}"
            ),
        )
    if degraded:
        logger.warning(
            "pattern.score_capability_list.degraded",
            extra={
                "correlation_id": correlation_id,
                "capabilities": len(capabilities),
                "scored": scored,
                "degraded_capabilities": degraded,
            },
        )
    return best_score


def score_capability_list_sync(
    capabilities: list[Any],
    task: str,
    *,
    reasoning_config: BaseAgentConfig | None = None,
    correlation_id: str | None = None,
) -> float:
    """Return the max score across a capability list from a sync context.

    Raises:
        ReasoningDegradedError: Every capability in the list degraded (#1981).
    """
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
    """Score every (agent, card) pair in one pass and return (agent, score).

    Covers only the agents the LLM judge could actually score: an agent whose
    every capability degraded (#1981) is EXCLUDED, never appended at 0.0.
    Ranking a degraded agent at zero is what let `scored.sort()` place it
    anywhere among the genuine no-matches -- and, when every agent degraded,
    made "best" a function of dict order rather than fit.

    Raises:
        ReasoningDegradedError: There was at least one card and EVERY agent
            degraded, so no ranking exists. Returning an empty list would be
            read by the pattern callers as "no suitable agent" and silently
            route to their round-robin fallback.
    """
    scored: list[tuple[Any, float]] = []
    degraded: list[str] = []
    degraded_model = "unknown"

    for agent, card in agent_cards:
        capabilities = getattr(card, "primary_capabilities", None) or []
        try:
            score = await _score_capability_list_async(
                capabilities, task, reasoning_config, correlation_id
            )
        except ReasoningDegradedError as exc:
            degraded.append(getattr(agent, "agent_id", None) or str(agent))
            degraded_model = exc.model
            logger.warning(
                "pattern.rank_agents.agent_degraded",
                extra={
                    "correlation_id": correlation_id,
                    "agent_id": getattr(agent, "agent_id", None),
                    "model": exc.model,
                    "error": exc.error,
                },
            )
            continue

        scored.append((agent, score))

    if degraded:
        if not scored:
            raise ReasoningDegradedError(
                "pattern.rank_agents_by_capability",
                model=degraded_model,
                correlation_id=correlation_id,
                error=(
                    f"the capability judge degraded for all "
                    f"{len(agent_cards)} candidate agent(s): "
                    f"{', '.join(degraded)}"
                ),
            )
        logger.warning(
            "pattern.rank_agents.degraded",
            extra={
                "correlation_id": correlation_id,
                "candidates": len(agent_cards),
                "ranked": len(scored),
                "degraded_agents": degraded,
            },
        )
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

    Agents whose capability scoring degraded (#1981) are omitted from the
    result. The list is therefore SHORTER than *agent_cards* on a partially
    degraded round -- callers indexing `scored[0]` stay safe because an
    all-degraded round raises rather than returning an empty list.

    Raises:
        ReasoningDegradedError: Every candidate agent degraded (#1981).
    """
    cid = correlation_id or f"pattern_{uuid.uuid4().hex[:8]}"
    return _run_coroutine(_rank_agents_async(agent_cards, task, reasoning_config, cid))
