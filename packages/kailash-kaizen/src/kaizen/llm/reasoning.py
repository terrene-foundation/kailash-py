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

Structured output (#1981):
    Both agents request structured output derived from THEIR OWN signature.
    Providers whose wire carries a schema (OpenAI family) get a strict
    `json_schema` and the provider itself guarantees the score field exists;
    the rest get `json_object` plus an explicit JSON instruction in the
    system prompt, which is the only thing that makes a provider without a
    `response_format` parameter (Anthropic `/v1/messages`) answer in a
    parseable shape. Without both halves the model answers in prose, the
    score never arrives, and every candidate ties at 0.0.

Degradation:
    A judgment that arrives without a usable score raises
    `ReasoningDegradedError` rather than returning 0.0. A degraded judgment
    and a genuine "no match" are the same float, so a numeric return cannot
    express the difference — see the exception's docstring.

Caching:
    LLM similarity / capability judgments are memoised per (model, inputs)
    tuple for the lifetime of the agent. Patterns that loop over candidates
    (router, ensemble, supervisor) therefore issue one LLM call per unique
    (task, capability) pair even if the same comparison is requested
    repeatedly inside one selection round. Only VALID judgments are cached.

Observability:
    Every invocation emits entry and exit log lines with correlation_id,
    model, and latency_ms per `rules/observability.md` §1.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Tuple

from kaizen.config.providers import ConfigurationError
from kaizen.core._provider_env import _keyless_mock_allowed
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.core.prompt_utils import generate_prompt_from_signature, json_prompt_suffix
from kaizen.core.structured_output import StructuredOutput
from kaizen.signatures import InputField, OutputField, Signature

logger = logging.getLogger(__name__)

__all__ = [
    "ReasoningDegradedError",
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
# Errors
# ---------------------------------------------------------------------------


class ReasoningDegradedError(Exception):
    """The LLM judge returned without a usable score (#1981).

    Raised instead of returning a fabricated ``0.0``. A degraded judgment and
    a genuine "no match" are the SAME float, so a numeric return cannot
    express the difference: every caller that ranks candidates would tie them
    all at zero and pick whichever the sort emitted first. A typed exception
    is the one shape an existing caller cannot silently coerce back to zero.

    Attributes:
        helper: Name of the helper that degraded (``llm_capability_match`` /
            ``llm_text_similarity``).
        model: Model the judgment was dispatched to.
        correlation_id: Correlation ID shared with the ``*.degraded`` WARN
            line, so the log and the exception can be joined during triage.
        error: The underlying failure — the strategy's ``error`` value (e.g.
            ``"JSON_PARSE_FAILED"``) or a description of the unusable score.
            Provider exceptions reach this field already sanitised by
            ``LLMAgentNode._provider_llm_response``.
        raw_response: The model's actual answer when one was returned. The
            live #1981 case had a correct ``0.92`` in prose here — keeping it
            reachable is what lets a caller tell "the model was wrong" from
            "the number did not survive the transport".
    """

    def __init__(
        self,
        helper: str,
        *,
        model: str,
        correlation_id: str,
        error: str,
        raw_response: Optional[str] = None,
    ) -> None:
        self.helper = helper
        self.model = model
        self.correlation_id = correlation_id
        self.error = error
        self.raw_response = raw_response
        super().__init__(
            f"{helper} returned no usable score (model={model}, "
            f"correlation_id={correlation_id}): {error}"
        )


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
# Structured output
# ---------------------------------------------------------------------------


def _structured_output_for(
    signature: Signature, provider: Optional[str]
) -> Dict[str, Any]:
    """Return the `response_format` a reasoning agent must request (#1981).

    Delegates to the framework primitive `StructuredOutput.for_provider`, so
    the per-provider translation lives in ONE place: OpenAI-family providers
    get a strict `json_schema` (constrained sampling — the provider itself
    guarantees the score field exists); everything else gets `json_object`,
    which each wire protocol renders as it can (Ollama's top-level `format`,
    Cohere's `response_format.schema`) or drops when the provider has no
    equivalent (Anthropic `/v1/messages`).

    The schema is ALWAYS derived from the reasoning signature passed here,
    never from a caller-supplied config: `runtime.py` / `registry.py` hand
    the HOST agent's config to the judge so the model selection is shared,
    and copying that config's `response_format` would force the judge to
    answer in a schema with no score field at all.
    """
    return StructuredOutput.from_signature(signature).for_provider(provider or "")


def _provider_enforces_schema(response_format: Optional[Dict[str, Any]]) -> bool:
    """True when the PROVIDER guarantees the shape (strict `json_schema`)."""
    return (
        isinstance(response_format, dict)
        and response_format.get("type") == "json_schema"
    )


def _reasoning_system_prompt(
    role: str, signature: Signature, response_format: Optional[Dict[str, Any]]
) -> str:
    """Compose role prose + the signature's output contract (#1981).

    The role paragraph alone names no output field and never says "JSON", so
    a model that is not schema-constrained answers in prose and the score is
    lost in transport. `generate_prompt_from_signature` is the framework's
    single source of truth for the field listing; `json_prompt_suffix` adds
    the explicit JSON instruction — appended ONLY when the provider does not
    already enforce the schema, per `create_structured_output_config`'s
    contract (strict mode needs no prompt-level restatement).
    """
    parts = [role, "", generate_prompt_from_signature(signature)]
    if not _provider_enforces_schema(response_format):
        parts.append(json_prompt_suffix(getattr(signature, "output_fields", None)))
    return "\n".join(parts)


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

    _ROLE = (
        "You are a semantic similarity judge. Given two texts, rate how "
        "close their meaning is on a 0.0-1.0 scale and justify the score "
        "in one sentence. Focus on intent and topic, not surface wording."
    )

    def _default_signature(self) -> Signature:
        return TextSimilaritySignature()

    def _generate_system_prompt(self) -> str:
        return _reasoning_system_prompt(
            self._ROLE, self.signature, self.config.response_format
        )


class CapabilityMatchAgent(BaseAgent):
    """BaseAgent that delegates capability matching to the LLM.

    Uses `CapabilityMatchSignature`. Same determinism and MCP considerations
    as `TextSimilarityAgent`.
    """

    _ROLE = (
        "You are a capability matcher for multi-agent routing. Given an "
        "agent capability (name + description) and a task requirement, "
        "decide if the capability can fulfil the requirement and return a "
        "confidence score on a 0.0-1.0 scale. Reason about intent and "
        "domain overlap, not keyword presence."
    )

    def _default_signature(self) -> Signature:
        return CapabilityMatchSignature()

    def _generate_system_prompt(self) -> str:
        return _reasoning_system_prompt(
            self._ROLE, self.signature, self.config.response_format
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

    Structured output is NOT resolved here — it depends on which reasoning
    signature the agent will run, which only the `get_*_agent` factories
    know. They pass this config through `_with_structured_output` (#1981).
    A caller-supplied `response_format` is deliberately dropped rather than
    cloned: `runtime.py` / `registry.py` hand the HOST agent's config to the
    judge so the model selection is shared, and the host's schema has no
    score field in it.

    If no model is configured (neither `OPENAI_PROD_MODEL` nor
    `DEFAULT_LLM_MODEL`), this FAILS LOUD with a typed `ConfigurationError`
    rather than silently returning a `mock` config that would fabricate
    reasoning as a real answer (#1952 same-class as the keyless-provider
    fail-loud). The `mock` config is returned ONLY under the explicit
    test-harness opt-in `KAIZEN_ALLOW_KEYLESS_MOCK` — real callers always
    route through a real model or an explicit config.
    """
    if config is None:
        model = os.environ.get("OPENAI_PROD_MODEL") or os.environ.get(
            "DEFAULT_LLM_MODEL"
        )
        provider = os.environ.get("DEFAULT_LLM_PROVIDER")
        if not model:
            # #1952 same-class: a keyless/modelless REAL caller must fail loud,
            # not silently get mock reasoning presented as a real answer. Mock
            # is returned ONLY under the explicit test-harness opt-in, mirroring
            # detect_provider_from_env()'s keyless contract.
            if not _keyless_mock_allowed():
                raise ConfigurationError(
                    "No model configured for the reasoning agent: set "
                    "OPENAI_PROD_MODEL or DEFAULT_LLM_MODEL, or pass an explicit "
                    "config. Refusing to silently dispatch the mock provider "
                    "(which would fabricate reasoning as a real answer)."
                )
            # Explicit test/offline opt-in only: mock provider.
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

    # Clone and harden. `response_format` is deliberately absent — see the
    # docstring; `_with_structured_output` supplies the correct one.
    return BaseAgentConfig(
        llm_provider=config.llm_provider,
        model=config.model,
        temperature=0.0,
        max_tokens=config.max_tokens,
        provider_config=config.provider_config,
        api_key=config.api_key,
        base_url=config.base_url,
        mcp_enabled=False,
    )


def _with_structured_output(
    config: BaseAgentConfig, signature: Signature
) -> BaseAgentConfig:
    """Return `config` with structured output derived from `signature` (#1981).

    Applied by the `get_*_agent` factories, which are the only places that
    know which reasoning signature the agent will run. `replace` is used so a
    field added to `BaseAgentConfig` later cannot be silently dropped by a
    hand-listed re-construction.
    """
    return replace(
        config,
        response_format=_structured_output_for(signature, config.llm_provider),
        structured_output_mode="explicit",
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
    resolved = _with_structured_output(
        _resolve_reasoning_config(config), TextSimilaritySignature()
    )
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
    resolved = _with_structured_output(
        _resolve_reasoning_config(config), CapabilityMatchSignature()
    )
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


def _usable_score(value: Any) -> Optional[float]:
    """Clamp a judge-supplied score to [0.0, 1.0], or None when unusable.

    Returning None instead of a default is the point (#1981): a score the
    judge never produced — absent, prose, NaN, a bool — is NOT zero. The old
    `float(value)`-with-default form turned every unusable value into a
    plausible 0.0 that ranked identically to a genuine no-match.

    `bool` is rejected explicitly: it is an `int` subclass, so `float(True)`
    is 1.0 — a model answering `"match_score": true` would otherwise be read
    as a perfect-confidence match.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
    elif isinstance(value, str):
        try:
            score = float(value.strip())
        except (TypeError, ValueError):
            return None
    else:
        return None
    if score != score:  # NaN — comparisons below would silently pass it through
        return None
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """Clamped float for values already known to be usable (cache reads)."""
    score = _usable_score(value)
    return default if score is None else score


def _degradation_reason(result: Dict[str, Any], score_field: str) -> Optional[str]:
    """Describe why `result` carries no usable score, or None when it does.

    Three shapes reach here, all of which used to collapse to a fabricated
    0.0: the strategy's error envelope (`JSON_PARSE_FAILED`, a sanitised
    provider error, a signature-validation failure), an absent score field,
    and a present-but-unusable value.
    """
    error = result.get("error")
    if error:
        return str(error)
    raw = result.get(score_field)
    if raw is None:
        return f"response carried no {score_field}"
    if _usable_score(raw) is None:
        return (
            f"{score_field} was not a usable number "
            f"(got {type(raw).__name__}: {raw!r})"
        )
    return None


def _raw_response_of(result: Dict[str, Any]) -> Optional[str]:
    """Best-effort text of what the model actually said, for triage."""
    response = result.get("response")
    if response is None:
        return None
    return response if isinstance(response, str) else str(response)


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
        float: Similarity in [0.0, 1.0]. ``0.0`` here always means the LLM
        judged the texts unrelated — a judgment that did not arrive raises
        instead (see below), so the two are distinguishable.

    Raises:
        ReasoningDegradedError: The judge returned without a usable
            similarity (#1981) — e.g. the provider answered in prose and
            structured-output parsing failed. Sibling contract of
            `llm_capability_match`; see its Raises section for the rationale.
        Exception: Whatever the agent raised, propagated unchanged.
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
        # ``agent.run`` above IS the provider dispatch, so this exception
        # routinely carries the provider's auth error text. TWO surfaces leaked
        # here: the ``error`` field (raw ``str(exc)``) AND the traceback that
        # ``logger.exception`` emits — dropping exc_info is what stops the raw
        # message re-entering via the traceback's final line (#1970 sweep;
        # observability.md Rule 6.3). The bare ``raise`` is deliberate: the
        # caller owns what it does with the exception object itself.
        from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

        logger.error(
            "llm_text_similarity.error",
            extra={
                "correlation_id": cid,
                "model": model,
                "latency_ms": latency_ms,
                "error": sanitize_provider_error(exc, "llm_text_similarity"),
            },
        )
        raise

    latency_ms = (time.monotonic() - t0) * 1000
    degradation = _degradation_reason(result, "similarity")

    if degradation is not None:
        # Sibling of the `llm_capability_match` degradation guard below — same
        # shape, same failure mode, fixed at both sites in one change so the
        # helpers cannot drift. See that guard for the full rationale.
        logger.warning(
            "llm_text_similarity.degraded",
            extra={
                "correlation_id": cid,
                "model": model,
                "latency_ms": latency_ms,
                "error": degradation,
            },
        )
        raise ReasoningDegradedError(
            "llm_text_similarity",
            model=model,
            correlation_id=cid,
            error=degradation,
            raw_response=_raw_response_of(result),
        )

    similarity = _coerce_float(result.get("similarity"))
    _CACHE._similarity_results[cache_key] = result
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
        float: Match confidence in [0.0, 1.0]. ``0.0`` here always means the
        LLM judged the capability a non-match.

    Raises:
        ReasoningDegradedError: The judge returned without a usable
            `match_score` (#1981) — the provider answered in prose and
            structured-output parsing failed, the field was absent, or the
            value was not a number. Returning 0.0 for this case made a failed
            judgment indistinguishable from a genuine no-match, so callers
            that RANK capabilities tied every candidate at zero and picked
            whichever the sort emitted first. A caller that would rather
            drop one judgment than fail a whole round should catch this
            explicitly — the point is that it can no longer happen by
            accident.
        Exception: Whatever the agent raised, propagated unchanged (already
            logged at `llm_capability_match.error`).
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
        # Sibling of the llm_text_similarity guard above — same provider-dispatch
        # seam, same two leak surfaces (raw ``error`` field + exc_info traceback),
        # kept in lockstep per security.md § Multi-Site Kwarg Plumbing (#1970).
        from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

        logger.error(
            "llm_capability_match.error",
            extra={
                "correlation_id": cid,
                "model": model,
                "latency_ms": latency_ms,
                "error": sanitize_provider_error(exc, "llm_capability_match"),
            },
        )
        raise

    latency_ms = (time.monotonic() - t0) * 1000
    degradation = _degradation_reason(result, "match_score")

    if degradation is not None:
        # The agent returned WITHOUT a usable score — e.g. the provider emitted
        # prose and structured-output parsing failed ("JSON_PARSE_FAILED"), so
        # `match_score` is absent. Returning the 0.0 that
        # `_coerce_float(None)` produced tied every capability at zero and made
        # the caller's ranking arbitrary — a fabricated answer presented as a
        # real one (zero-tolerance.md Rule 3), and unreachable by the caller
        # because it lived only in a log line. #1981 raises instead: WARN keeps
        # the degradation triageable (observability.md MUST Rule 3) and the
        # typed error makes it impossible to consume as a score.
        #
        # The degraded result is deliberately NOT cached: the cache exists to
        # avoid recomputing a VALID score, and memoising a parse failure would
        # pin the failure for this (model, capability, requirement) key for the
        # rest of the process — outliving the transient condition that caused
        # it.
        logger.warning(
            "llm_capability_match.degraded",
            extra={
                "correlation_id": cid,
                "model": model,
                "latency_ms": latency_ms,
                "capability_name": capability_name,
                "error": degradation,
            },
        )
        raise ReasoningDegradedError(
            "llm_capability_match",
            model=model,
            correlation_id=cid,
            error=degradation,
            raw_response=_raw_response_of(result),
        )

    score = _coerce_float(result.get("match_score"))
    _CACHE._match_results[cache_key] = result
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
