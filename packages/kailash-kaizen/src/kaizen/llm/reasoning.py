"""
LLM-first reasoning helpers for similarity and capability matching.

This module provides Kaizen Signature-backed helpers that replace the legacy
keyword/substring/Jaccard scoring used by A2A routing and multi-agent pattern
selection. The LLM is the reasoner; these helpers are thin wrappers that
delegate to a BaseAgent and return the structured output the caller needs.

Why this exists:
    `rules/agent-reasoning.md` MUST Rule 1 forbids deterministic logic in agent
    decision paths. The previous implementation used Jaccard word-set overlap
    (`runtime._simple_text_similarity`) and substring containment
    (`Capability.matches_requirement`) to route tasks between agents. Both are
    BLOCKED because they fail on paraphrased input, synonyms, and anything the
    keyword set does not literally contain.

    This module replaces that logic with signature-driven LLM reasoning that
    generalises across natural language variation while remaining observable
    and cacheable.

Caching:
    LLM similarity / capability judgments are memoised per (model, inputs)
    tuple for the lifetime of the agent. Patterns that loop over candidates
    (router, ensemble, supervisor) therefore issue one LLM call per unique
    (task, capability) pair even if the same comparison is requested
    repeatedly inside one selection round.

Observability:
    Every invocation emits entry and exit log lines with correlation_id,
    model, and latency_ms per `rules/observability.md` §1.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature

logger = logging.getLogger(__name__)

__all__ = [
    "TextSimilaritySignature",
    "CapabilityMatchSignature",
    "TextSimilarityAgent",
    "CapabilityMatchAgent",
    "llm_text_similarity",
    "llm_capability_match",
    "get_text_similarity_agent",
    "get_capability_match_agent",
    "clear_reasoning_cache",
]


# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------


class TextSimilaritySignature(Signature):
    """Compute semantic similarity between two pieces of text.

    The LLM reads both strings and returns a single floating-point score
    between 0.0 (unrelated) and 1.0 (identical meaning). The reasoning field
    MUST explain why the LLM assigned the score so the decision is traceable.
    """

    text_a: str = InputField(description="First text to compare")
    text_b: str = InputField(description="Second text to compare against the first")
    similarity: float = OutputField(
        description=(
            "Semantic similarity score on a 0.0-1.0 scale. "
            "1.0 = identical meaning; 0.8-0.99 = same topic, paraphrased; "
            "0.4-0.79 = related topic; 0.0-0.39 = unrelated."
        )
    )
    reasoning: str = OutputField(
        description="One sentence explaining why this score was assigned"
    )


class CapabilityMatchSignature(Signature):
    """Decide whether an agent capability fulfils a task requirement.

    The LLM receives a capability card (name, description) and a requirement
    string, then decides if the capability is a good fit. A confidence score
    on a 0.0-1.0 scale accompanies the boolean decision so callers can rank
    multiple capabilities.
    """

    capability_name: str = InputField(
        description="Short name of the agent capability (e.g. 'code_generation')"
    )
    capability_description: str = InputField(
        description="Human-readable description of what the capability does"
    )
    requirement: str = InputField(
        description="Task requirement the caller needs fulfilled"
    )
    matches: bool = OutputField(
        description="True if the capability can fulfil the requirement"
    )
    match_score: float = OutputField(
        description=(
            "Confidence on a 0.0-1.0 scale. 1.0 = perfect match; "
            "0.8-0.99 = strong match; 0.5-0.79 = partial match; "
            "0.0-0.49 = weak or no match."
        )
    )
    reasoning: str = OutputField(description="One sentence explaining the decision")


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class TextSimilarityAgent(BaseAgent):
    """BaseAgent that delegates text similarity to the LLM.

    Uses `TextSimilaritySignature`. The agent is deterministic by default
    (temperature 0.0) so the similarity score is stable across identical
    inputs. MCP discovery is disabled because the agent only needs to reason
    about its structured inputs.
    """

    def _default_signature(self) -> Signature:
        return TextSimilaritySignature()

    def _generate_system_prompt(self) -> str:
        return (
            "You are a semantic similarity judge. Given two texts, rate how "
            "close their meaning is on a 0.0-1.0 scale and justify the score "
            "in one sentence. Focus on intent and topic, not surface wording."
        )


class CapabilityMatchAgent(BaseAgent):
    """BaseAgent that delegates capability matching to the LLM.

    Uses `CapabilityMatchSignature`. Same determinism and MCP considerations
    as `TextSimilarityAgent`.
    """

    def _default_signature(self) -> Signature:
        return CapabilityMatchSignature()

    def _generate_system_prompt(self) -> str:
        return (
            "You are a capability matcher for multi-agent routing. Given an "
            "agent capability (name + description) and a task requirement, "
            "decide if the capability can fulfil the requirement and return a "
            "confidence score on a 0.0-1.0 scale. Reason about intent and "
            "domain overlap, not keyword presence."
        )


# ---------------------------------------------------------------------------
# Agent + result caching
# ---------------------------------------------------------------------------


@dataclass
class _ReasoningCache:
    """In-process cache for reasoning agents and their results.

    Two layers:
        - `_agents`: one agent instance per (llm_provider, model, temperature)
          tuple, so we do not re-initialise BaseAgent on every call.
        - `_similarity_results` / `_match_results`: memoise result per
          (model, inputs) tuple so loops that compare one task against N
          capabilities only fire N LLM calls even if the caller retries.
    """

    _agents: Dict[Tuple[str, Any, str, float], BaseAgent] = field(default_factory=dict)
    _similarity_results: Dict[Tuple[str, str, str], Dict[str, Any]] = field(
        default_factory=dict
    )
    _match_results: Dict[Tuple[str, str, str, str], Dict[str, Any]] = field(
        default_factory=dict
    )


_CACHE = _ReasoningCache()


def clear_reasoning_cache() -> None:
    """Clear the reasoning agent + result cache.

    Tests call this between runs to guarantee a clean LLM invocation count.
    Production callers MUST NOT call this in a hot path — the cache is the
    only thing preventing a fan-out of LLM calls.
    """
    _CACHE._agents.clear()
    _CACHE._similarity_results.clear()
    _CACHE._match_results.clear()


def _resolve_reasoning_config(
    config: Optional[BaseAgentConfig],
) -> BaseAgentConfig:
    """Return a config suitable for a reasoning agent.

    If the caller provides a config, clone it with temperature 0.0 and MCP
    auto-discovery disabled so the reasoning agent stays deterministic and
    cheap. If no config is supplied, fall back to `.env`-defined model with
    the same defaults per `rules/env-models`.

    Last-resort fallback is the `mock` provider: this keeps unit tests that
    pass bare `Mock(spec=BaseAgent)` stubs working without real API keys,
    while production paths always route through an explicit config.
    """
    if config is None:
        model = os.environ.get("OPENAI_PROD_MODEL") or os.environ.get(
            "DEFAULT_LLM_MODEL"
        )
        provider = os.environ.get("DEFAULT_LLM_PROVIDER")
        if not model:
            # Last-resort test/offline fallback: mock provider.
            return BaseAgentConfig(
                llm_provider="mock",
                model="mock-model",
                temperature=0.0,
                mcp_enabled=False,
            )
        return BaseAgentConfig(
            llm_provider=provider or "openai",
            model=model,
            temperature=0.0,
            mcp_enabled=False,
        )

    # Clone and harden
    return BaseAgentConfig(
        llm_provider=config.llm_provider,
        model=config.model,
        temperature=0.0,
        max_tokens=config.max_tokens,
        provider_config=config.provider_config,
        response_format=config.response_format,
        structured_output_mode=config.structured_output_mode,
        api_key=config.api_key,
        base_url=config.base_url,
        mcp_enabled=False,
    )


def _agent_cache_key(config: BaseAgentConfig, kind: str) -> Tuple[str, Any, str, float]:
    return (
        kind,
        config.llm_provider or "default",
        config.model or "default",
        float(config.temperature or 0.0),
    )


def get_text_similarity_agent(
    config: Optional[BaseAgentConfig] = None,
) -> TextSimilarityAgent:
    """Return a cached `TextSimilarityAgent` for the resolved config."""
    resolved = _resolve_reasoning_config(config)
    key = _agent_cache_key(resolved, "text_similarity")
    agent = _CACHE._agents.get(key)
    if agent is None:
        agent = TextSimilarityAgent(
            config=resolved,
            mcp_servers=[],  # reasoning is pure, no tools
        )
        _CACHE._agents[key] = agent
    return agent  # type: ignore[return-value]


def get_capability_match_agent(
    config: Optional[BaseAgentConfig] = None,
) -> CapabilityMatchAgent:
    """Return a cached `CapabilityMatchAgent` for the resolved config."""
    resolved = _resolve_reasoning_config(config)
    key = _agent_cache_key(resolved, "capability_match")
    agent = _CACHE._agents.get(key)
    if agent is None:
        agent = CapabilityMatchAgent(
            config=resolved,
            mcp_servers=[],
        )
        _CACHE._agents[key] = agent
    return agent  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def llm_text_similarity(
    text_a: str,
    text_b: str,
    *,
    config: Optional[BaseAgentConfig] = None,
    correlation_id: Optional[str] = None,
) -> float:
    """Compute semantic similarity between two strings via the LLM.

    This is the LLM-first replacement for Jaccard word-set overlap. The LLM
    receives both strings and returns a 0.0-1.0 score. Results are cached per
    (model, text_a, text_b) to keep loops cheap.

    Args:
        text_a: First string.
        text_b: Second string to compare against.
        config: Optional BaseAgentConfig for model selection. When None, the
            helper falls back to .env-defined model + provider.
        correlation_id: Optional correlation ID propagated to log lines. A
            fresh UUID is generated if not supplied.

    Returns:
        float: Similarity in [0.0, 1.0].
    """
    if not text_a or not text_b:
        return 0.0

    resolved = _resolve_reasoning_config(config)
    model = resolved.model or "unknown"
    cache_key = (model, text_a, text_b)
    cached = _CACHE._similarity_results.get(cache_key)
    if cached is not None:
        return _coerce_float(cached.get("similarity"))

    # Also check symmetric key (similarity is commutative in semantics).
    reverse_key = (model, text_b, text_a)
    cached = _CACHE._similarity_results.get(reverse_key)
    if cached is not None:
        return _coerce_float(cached.get("similarity"))

    cid = correlation_id or f"sim_{uuid.uuid4().hex[:8]}"
    logger.info(
        "llm_text_similarity.start",
        extra={
            "correlation_id": cid,
            "model": model,
            "text_a_len": len(text_a),
            "text_b_len": len(text_b),
        },
    )
    t0 = time.monotonic()

    try:
        agent = get_text_similarity_agent(resolved)
        result = agent.run(text_a=text_a, text_b=text_b)
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        logger.exception(
            "llm_text_similarity.error",
            extra={
                "correlation_id": cid,
                "model": model,
                "latency_ms": latency_ms,
                "error": str(exc),
            },
        )
        raise

    latency_ms = (time.monotonic() - t0) * 1000
    _CACHE._similarity_results[cache_key] = result
    similarity = _coerce_float(result.get("similarity"))
    logger.info(
        "llm_text_similarity.ok",
        extra={
            "correlation_id": cid,
            "model": model,
            "latency_ms": latency_ms,
            "similarity": similarity,
        },
    )
    return similarity


def llm_capability_match(
    capability_name: str,
    capability_description: str,
    requirement: str,
    *,
    config: Optional[BaseAgentConfig] = None,
    correlation_id: Optional[str] = None,
) -> float:
    """Score how well a capability matches a requirement via the LLM.

    This is the LLM-first replacement for substring scoring in
    `Capability.matches_requirement`. The LLM reads the capability card plus
    the requirement and returns a 0.0-1.0 match score. Results are cached per
    (model, name, description, requirement).

    Args:
        capability_name: Short name of the capability.
        capability_description: Human-readable description.
        requirement: Task requirement string.
        config: Optional BaseAgentConfig. Falls back to .env as elsewhere.
        correlation_id: Optional correlation ID for logs.

    Returns:
        float: Match confidence in [0.0, 1.0].
    """
    if not requirement or not capability_name:
        return 0.0

    resolved = _resolve_reasoning_config(config)
    model = resolved.model or "unknown"
    cache_key = (model, capability_name, capability_description, requirement)
    cached = _CACHE._match_results.get(cache_key)
    if cached is not None:
        return _coerce_float(cached.get("match_score"))

    cid = correlation_id or f"match_{uuid.uuid4().hex[:8]}"
    logger.info(
        "llm_capability_match.start",
        extra={
            "correlation_id": cid,
            "model": model,
            "capability_name": capability_name,
            "requirement_len": len(requirement),
        },
    )
    t0 = time.monotonic()

    try:
        agent = get_capability_match_agent(resolved)
        result = agent.run(
            capability_name=capability_name,
            capability_description=capability_description or capability_name,
            requirement=requirement,
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        logger.exception(
            "llm_capability_match.error",
            extra={
                "correlation_id": cid,
                "model": model,
                "latency_ms": latency_ms,
                "error": str(exc),
            },
        )
        raise

    latency_ms = (time.monotonic() - t0) * 1000
    _CACHE._match_results[cache_key] = result
    score = _coerce_float(result.get("match_score"))
    logger.info(
        "llm_capability_match.ok",
        extra={
            "correlation_id": cid,
            "model": model,
            "latency_ms": latency_ms,
            "match_score": score,
            "matches": bool(result.get("matches")),
        },
    )
    return score
