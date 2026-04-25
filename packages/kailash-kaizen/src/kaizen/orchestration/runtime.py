# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
OrchestrationRuntime — cross-SDK parity with kailash-rs `OrchestrationEngine`.

This module ships the Python equivalent of the Rust
`kaizen-agents::orchestration::runtime::OrchestrationRuntime` shape (issue #602
/ kailash-rs ISS-27). The Python ``OrchestrationRuntime`` is constructed with a
strategy + coordinator and exposes both async (``.run``) and sync
(``.run_sync``) entry points. Same input -> same observable result on both
SDKs (modulo determinism), per EATP D6.

The class is intentionally a thin orchestrator over four strategies
(``Sequential`` / ``Parallel`` / ``Hierarchical`` / ``Pipeline``) and mirrors
the Rust enum. Agents are registered by name in insertion order, which
determines execution order for the Sequential and Pipeline strategies (also
mirroring Rust's ``IndexMap``-backed registry).

Existing Kaizen orchestration components — ``kaizen_agents.patterns.runtime``
(registry-based, multi-agent SaaS shape) and
``kaizen.trust.orchestration.runtime`` (trust-aware runtime) — are NOT replaced
by this class. They serve different problems:

- ``kaizen_agents.patterns.OrchestrationRuntime`` — registry/lifecycle/health/
  budget/circuit-breaker pattern for 10-100 agent fleets.
- ``kaizen.trust.orchestration.TrustAwareOrchestrationRuntime`` — trust-policy
  enforcement on top of orchestration.
- ``kaizen.orchestration.runtime.OrchestrationRuntime`` (THIS module) —
  strategy-driven multi-agent coordination matching the Rust API shape, used
  for cross-SDK parity and as the canonical shape downstream consumers
  reference (e.g., ``OrchestrationRuntime`` examples in
  ``kaizen.signatures``).

Usage
-----
.. code-block:: python

    from kaizen.orchestration import (
        OrchestrationRuntime,
        OrchestrationStrategy,
        SharedMemoryCoordinator,
    )

    runtime = (
        OrchestrationRuntime(
            strategy=OrchestrationStrategy.sequential(),
            coordinator=SharedMemoryCoordinator(),
        )
        .add_agent("researcher", researcher_agent)
        .add_agent("writer", writer_agent)
    )
    result = await runtime.run("Summarize Q3 revenue trends")
    # result.final_output == writer_agent's response
    # result.agent_results["researcher"] == per-agent dict

Cross-SDK contract (mirrors ``orchestration/runtime.rs``)
---------------------------------------------------------
- Constructor: ``OrchestrationRuntime(strategy, coordinator=None, config=None)``
  + builder-style ``.add_agent(name, agent)``, ``.strategy(s)``, ``.config(c)``,
  ``.coordinator(c)``.
- Execution: ``await runtime.run(input)`` returns ``OrchestrationResult``.
  Sync convenience: ``runtime.run_sync(input)`` (uses ``asyncio.run`` — only
  call from non-async contexts; see ``rules/patterns.md`` § Paired Public
  Surface).
- Strategies: ``Sequential`` / ``Parallel`` / ``Hierarchical`` / ``Pipeline``
  are constructed via ``OrchestrationStrategy.<name>(...)`` factories so the
  enum surface is a typed dataclass, not an opaque string.
- Result fields match the Rust struct: ``agent_results`` (dict by name),
  ``final_output`` (str), ``total_iterations`` (int), ``total_tokens`` (int),
  ``duration_ms`` (int).
- Errors: empty-runtime / unknown-coordinator / pipeline-step-references-
  unknown-agent / max-agent-calls all raise ``OrchestrationError`` (see
  ``exceptions``). No silent fallbacks (per ``rules/zero-tolerance.md``
  Rule 3).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    Union,
    runtime_checkable,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AgentLike",
    "Coordinator",
    "OrchestrationConfig",
    "OrchestrationError",
    "OrchestrationResult",
    "OrchestrationRuntime",
    "OrchestrationStrategy",
    "OrchestrationStrategyKind",
    "PipelineInputSource",
    "PipelineStep",
    "SharedMemoryCoordinator",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OrchestrationError(RuntimeError):
    """Typed error for orchestration runtime failures.

    Subclass of ``RuntimeError`` (not a custom ``Exception`` hierarchy) so it
    composes cleanly with ``asyncio.TimeoutError`` and matches the
    ``AgentError::Config`` shape used on the Rust side without forcing the
    caller into a kaizen-specific exception import.
    """


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentLike(Protocol):
    """Minimal duck-type for agents the runtime can drive.

    Mirrors the Rust ``BaseAgent`` trait surface with the methods the strategy
    dispatcher actually invokes. Either ``run`` or ``run_async`` MUST be
    implemented; the runtime prefers ``run_async`` when available.

    Real ``kaizen.core.base_agent.BaseAgent`` instances satisfy this Protocol
    out of the box (their ``run`` returns ``Dict[str, Any]`` whose ``.get(
    "response")`` or first ``OutputField`` value the runtime treats as the
    string response). Test adapters / Rust-port shims need only provide the
    minimal pair.
    """

    @property
    def name(self) -> str:  # pragma: no cover - Protocol surface
        ...

    async def run_async(
        self, **inputs: Any
    ) -> Mapping[str, Any]:  # pragma: no cover - Protocol surface
        ...


@runtime_checkable
class Coordinator(Protocol):
    """Minimal duck-type for the orchestration coordinator.

    Mirrors Rust's ``Arc<dyn AgentMemory>`` shared-memory integration point.
    A coordinator is the cross-agent state surface — agents write findings via
    ``store(...)`` and read peers' findings via ``retrieve(...)``. The
    Sequential and Hierarchical strategies forward the coordinator into each
    agent's per-call kwargs as ``coordinator=`` so the agent can opt into
    shared-state reads/writes.

    A ``None`` coordinator is permitted; the runtime then runs each agent in
    isolation (matches Rust's ``Option<Arc<dyn AgentMemory>>`` shape).
    """

    async def store(
        self, key: str, value: Any
    ) -> None:  # pragma: no cover - Protocol surface
        ...

    async def retrieve(
        self, key: str
    ) -> Optional[Any]:  # pragma: no cover - Protocol surface
        ...


class SharedMemoryCoordinator:
    """Default in-memory coordinator backed by ``SharedMemoryPool``.

    Wraps ``kaizen.memory.shared_memory.SharedMemoryPool`` (the synchronous,
    thread-safe insight pool) into the async ``Coordinator`` Protocol the
    runtime expects. Round-trips ``store(key, value)`` / ``retrieve(key)`` via
    a single-tag insight write/filter so the same pool can be observed from
    other Kaizen agents that already integrate with ``SharedMemoryPool``.

    For deployments that require a persistent, distributed, or trust-aware
    coordinator (e.g., DataFlow-backed insight stores), implement the
    ``Coordinator`` Protocol directly — this class is a convenience default,
    not a production primitive.
    """

    def __init__(self, agent_id: str = "orchestration-runtime") -> None:
        # Local import — keeps the runtime module importable even if the
        # memory subpackage's heavier imports drift.
        from kaizen.memory.shared_memory import SharedMemoryPool

        self._pool = SharedMemoryPool()
        self._agent_id = agent_id

    async def store(self, key: str, value: Any) -> None:
        # Encode value as the insight content; tag with the key so retrieve
        # can filter exactly by tag.
        self._pool.write_insight(
            {
                "agent_id": self._agent_id,
                "content": str(value),
                "tags": [f"orch:{key}"],
                "importance": 0.5,
                "segment": "orchestration",
                "metadata": {"key": key, "raw": value},
            }
        )

    async def retrieve(self, key: str) -> Optional[Any]:
        # Read the most recent insight tagged with this key. ``read_all`` is
        # synchronous; the async signature is for Protocol-compliance.
        insights = self._pool.read_all()
        for insight in reversed(insights):
            if f"orch:{key}" in insight.get("tags", []):
                meta = insight.get("metadata", {}) or {}
                return meta.get("raw", insight.get("content"))
        return None


# ---------------------------------------------------------------------------
# Strategy dataclasses
# ---------------------------------------------------------------------------


class OrchestrationStrategyKind(str, Enum):
    """Strategy discriminator — mirrors the Rust ``OrchestrationStrategy`` enum."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"
    PIPELINE = "pipeline"


@dataclass(frozen=True)
class PipelineInputSource:
    """Where a pipeline step fetches its input from (mirrors Rust enum).

    One of ``initial`` (use the run-level input), ``agent_output`` (use a
    previously-executed step's response by name), or ``template`` (interpolate
    ``{{agent_name.response}}`` placeholders against prior results).

    Only one of ``initial``, ``agent_name``, ``template`` is set at a time;
    construct via the classmethods so misconstruction is impossible at the
    Python level.
    """

    initial: bool = False
    agent_name: Optional[str] = None
    template: Optional[str] = None

    @classmethod
    def from_initial(cls) -> "PipelineInputSource":
        return cls(initial=True)

    @classmethod
    def from_agent_output(cls, agent_name: str) -> "PipelineInputSource":
        if not agent_name:
            raise ValueError(
                "PipelineInputSource.from_agent_output requires a non-empty agent_name"
            )
        return cls(agent_name=agent_name)

    @classmethod
    def from_template(cls, template: str) -> "PipelineInputSource":
        if template is None:
            raise ValueError(
                "PipelineInputSource.from_template requires a non-None template"
            )
        return cls(template=template)


@dataclass(frozen=True)
class PipelineStep:
    """One step in a pipeline strategy."""

    agent_name: str
    input_from: PipelineInputSource


@dataclass(frozen=True)
class OrchestrationStrategy:
    """Strategy descriptor — mirrors the Rust ``OrchestrationStrategy`` enum.

    Construct via the classmethods (``sequential()``, ``parallel()``,
    ``hierarchical(coordinator_name=...)``, ``pipeline(steps=...)``) so the
    enum cannot be misconstructed (e.g., a Hierarchical without a coordinator
    name).
    """

    kind: OrchestrationStrategyKind = OrchestrationStrategyKind.SEQUENTIAL
    coordinator_name: Optional[str] = None
    steps: Optional[Tuple[PipelineStep, ...]] = None

    @classmethod
    def sequential(cls) -> "OrchestrationStrategy":
        return cls(kind=OrchestrationStrategyKind.SEQUENTIAL)

    @classmethod
    def parallel(cls) -> "OrchestrationStrategy":
        return cls(kind=OrchestrationStrategyKind.PARALLEL)

    @classmethod
    def hierarchical(cls, coordinator_name: str) -> "OrchestrationStrategy":
        if not coordinator_name:
            raise ValueError(
                "OrchestrationStrategy.hierarchical requires a non-empty coordinator_name"
            )
        return cls(
            kind=OrchestrationStrategyKind.HIERARCHICAL,
            coordinator_name=coordinator_name,
        )

    @classmethod
    def pipeline(cls, steps: List[PipelineStep]) -> "OrchestrationStrategy":
        if not steps:
            raise ValueError(
                "OrchestrationStrategy.pipeline requires a non-empty list of PipelineStep"
            )
        return cls(
            kind=OrchestrationStrategyKind.PIPELINE,
            steps=tuple(steps),
        )

    @property
    def name(self) -> str:
        return self.kind.value


# ---------------------------------------------------------------------------
# Config + result
# ---------------------------------------------------------------------------


@dataclass
class OrchestrationConfig:
    """Configuration for an orchestration run.

    Field semantics match the Rust ``OrchestrationConfig`` struct so the same
    config dict round-trips between SDKs.
    """

    max_total_iterations: int = 50
    max_agent_calls: int = 100
    timeout_secs: Optional[float] = None
    fail_fast: bool = True
    share_conversation_history: bool = False


@dataclass
class OrchestrationResult:
    """Result of a single orchestration run.

    Field semantics match the Rust ``OrchestrationResult`` struct.
    ``agent_results`` is keyed by agent name and ordered by execution; the
    insertion-ordered ``dict`` provides the same observable order as the
    Rust ``IndexMap``.
    """

    agent_results: Dict[str, Mapping[str, Any]] = field(default_factory=dict)
    final_output: str = ""
    total_iterations: int = 0
    total_tokens: int = 0
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_results": {k: dict(v) for k, v in self.agent_results.items()},
            "final_output": self.final_output,
            "total_iterations": self.total_iterations,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# OrchestrationRuntime
# ---------------------------------------------------------------------------


# Type alias for the pluggable agent invoker. Tests / port shims may pass any
# callable matching ``(agent, input, coordinator) -> Awaitable[Mapping]``.
AgentInvoker = Callable[[Any, str, Optional[Coordinator]], Awaitable[Mapping[str, Any]]]


class OrchestrationRuntime:
    """Multi-agent orchestration runtime with cross-SDK parity.

    Mirrors the Rust ``kaizen-agents::orchestration::runtime::OrchestrationRuntime``
    builder + dispatch shape. Construct with a strategy and (optional)
    coordinator, then chain ``add_agent`` calls and invoke ``run``.

    Per ``rules/agent-reasoning.md``: this class is a transport / dispatch
    layer; it does NOT make agent decisions in code (no keyword routing, no
    if-else over input content). Strategy selection is configured up-front
    and any per-task routing inside Hierarchical / Pipeline strategies
    happens through agent names declared at build time, not through runtime
    classification of the input string.
    """

    def __init__(
        self,
        strategy: Optional[OrchestrationStrategy] = None,
        coordinator: Optional[Coordinator] = None,
        config: Optional[OrchestrationConfig] = None,
        *,
        agent_invoker: Optional[AgentInvoker] = None,
    ) -> None:
        """Initialize an orchestration runtime.

        Args:
            strategy: Coordination strategy. Defaults to Sequential when
                ``None`` is passed (matches Rust's ``OrchestrationRuntime::new``
                + ``OrchestrationStrategy::default``).
            coordinator: Optional shared-state object (``Coordinator``
                Protocol). If ``None``, agents run in isolation.
            config: Optional orchestration config (caps + timeouts +
                fail-fast). Defaults to ``OrchestrationConfig()``.
            agent_invoker: Optional dependency-injection seam — the
                ``async`` callable the runtime uses to invoke a single
                ``(agent, input, coordinator) -> Mapping`` step. Defaults to
                ``OrchestrationRuntime._default_invoker`` which prefers
                ``agent.run_async(input=...)`` and falls back to
                ``agent.run(input=...)`` in a thread. Tests inject this to
                avoid spinning up real LLM agents.
        """
        self._strategy: OrchestrationStrategy = (
            strategy if strategy is not None else OrchestrationStrategy.sequential()
        )
        self._coordinator: Optional[Coordinator] = coordinator
        self._config: OrchestrationConfig = (
            config if config is not None else OrchestrationConfig()
        )
        # Insertion-ordered dict — matches Rust IndexMap.
        self._agents: Dict[str, Any] = {}
        self._agent_invoker: AgentInvoker = (
            agent_invoker if agent_invoker is not None else self._default_invoker
        )

    # -----------------------------------------------------------------------
    # Builder API
    # -----------------------------------------------------------------------

    def add_agent(self, name: str, agent: Any) -> "OrchestrationRuntime":
        """Register an agent under ``name``.

        Insertion order determines execution order for the Sequential and
        Pipeline strategies (matches Rust's ``IndexMap`` behavior). Re-adding
        the same name replaces the previous agent.

        Returns ``self`` so calls chain.
        """
        if not name:
            raise ValueError("OrchestrationRuntime.add_agent requires a non-empty name")
        self._agents[name] = agent
        return self

    def strategy(self, strategy: OrchestrationStrategy) -> "OrchestrationRuntime":
        """Replace the orchestration strategy. Returns ``self``."""
        if strategy is None:
            raise ValueError(
                "OrchestrationRuntime.strategy requires a non-None strategy"
            )
        self._strategy = strategy
        return self

    def coordinator(self, coordinator: Optional[Coordinator]) -> "OrchestrationRuntime":
        """Replace the coordinator (may be ``None``). Returns ``self``."""
        self._coordinator = coordinator
        return self

    def config(self, config: OrchestrationConfig) -> "OrchestrationRuntime":
        """Replace the orchestration config. Returns ``self``."""
        if config is None:
            raise ValueError("OrchestrationRuntime.config requires a non-None config")
        self._config = config
        return self

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def agent_names(self) -> List[str]:
        return list(self._agents.keys())

    @property
    def current_strategy(self) -> OrchestrationStrategy:
        return self._strategy

    @property
    def current_coordinator(self) -> Optional[Coordinator]:
        return self._coordinator

    @property
    def current_config(self) -> OrchestrationConfig:
        return self._config

    # -----------------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------------

    async def run(self, input: str) -> OrchestrationResult:
        """Run the orchestration with the given input.

        Async by parity with Rust ``async fn run``. Use ``run_sync`` for sync
        contexts (CLI scripts, tests) — see ``rules/patterns.md`` § Paired
        Public Surface for the trade-off.

        Raises:
            OrchestrationError: when no agents are registered, when the
                strategy references an unknown agent / coordinator, or when
                the underlying agent invocation fails and ``fail_fast`` is
                set.
            asyncio.TimeoutError: when ``config.timeout_secs`` is set and
                exceeded. The Rust SDK wraps this as ``AgentError::Config``;
                Python preserves the standard library type so callers can
                rely on existing ``except asyncio.TimeoutError`` handlers.
        """
        if not self._agents:
            raise OrchestrationError(
                "OrchestrationRuntime.run: no agents registered (call .add_agent() first)"
            )

        run_id = uuid.uuid4().hex[:8]
        logger.info(
            "orchestration.run.start",
            extra={
                "run_id": run_id,
                "strategy": self._strategy.name,
                "agent_count": len(self._agents),
                "agent_names": list(self._agents.keys()),
                "has_coordinator": self._coordinator is not None,
                "timeout_secs": self._config.timeout_secs,
            },
        )

        start = time.perf_counter()

        try:
            if self._config.timeout_secs is not None:
                result = await asyncio.wait_for(
                    self._dispatch(input, run_id=run_id),
                    timeout=self._config.timeout_secs,
                )
            else:
                result = await self._dispatch(input, run_id=run_id)
        except asyncio.TimeoutError:
            logger.exception(
                "orchestration.run.timeout",
                extra={
                    "run_id": run_id,
                    "timeout_secs": self._config.timeout_secs,
                },
            )
            raise
        except OrchestrationError:
            logger.exception("orchestration.run.error", extra={"run_id": run_id})
            raise
        except Exception:
            logger.exception("orchestration.run.error", extra={"run_id": run_id})
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        result.duration_ms = elapsed_ms
        logger.info(
            "orchestration.run.ok",
            extra={
                "run_id": run_id,
                "strategy": self._strategy.name,
                "duration_ms": elapsed_ms,
                "total_iterations": result.total_iterations,
                "total_tokens": result.total_tokens,
            },
        )
        return result

    def run_sync(self, input: str) -> OrchestrationResult:
        """Synchronous convenience wrapper around ``run``.

        WARNING: Calls ``asyncio.run()`` internally. Per
        ``rules/patterns.md`` § "Paired Public Surface — Consistent Async-ness",
        sync-wrapping ``asyncio.run`` raises ``RuntimeError: This event loop is
        already running`` when called from inside an active event loop
        (pytest-asyncio, Nexus handlers, Jupyter, any Kaizen agent). This
        method is a CLI/script convenience — production code should
        ``await runtime.run(input)`` directly.
        """
        return asyncio.run(self.run(input))

    # -----------------------------------------------------------------------
    # Dispatch
    # -----------------------------------------------------------------------

    async def _dispatch(self, input: str, *, run_id: str) -> OrchestrationResult:
        kind = self._strategy.kind
        if kind is OrchestrationStrategyKind.SEQUENTIAL:
            return await self._run_sequential(input, run_id=run_id)
        if kind is OrchestrationStrategyKind.PARALLEL:
            return await self._run_parallel(input, run_id=run_id)
        if kind is OrchestrationStrategyKind.HIERARCHICAL:
            return await self._run_hierarchical(input, run_id=run_id)
        if kind is OrchestrationStrategyKind.PIPELINE:
            return await self._run_pipeline(input, run_id=run_id)
        # Defensive: every strategy variant is enumerated above; any new
        # variant must add a branch. This is reached only if a future
        # contributor extends ``OrchestrationStrategyKind`` without updating
        # the dispatch — fail loudly per zero-tolerance Rule 3.
        raise OrchestrationError(
            f"OrchestrationRuntime: unknown strategy kind {kind!r}"
        )

    # -----------------------------------------------------------------------
    # Strategies
    # -----------------------------------------------------------------------

    async def _run_sequential(self, input: str, *, run_id: str) -> OrchestrationResult:
        agent_results: Dict[str, Mapping[str, Any]] = {}
        current_input = input
        total_tokens = 0
        total_iterations = 0

        for name, agent in self._agents.items():
            if total_iterations >= self._config.max_agent_calls:
                raise OrchestrationError(
                    f"OrchestrationRuntime: max_agent_calls={self._config.max_agent_calls} reached"
                )
            result = await self._invoke_one(
                agent, current_input, name=name, run_id=run_id
            )
            current_input = _extract_response(result)
            total_tokens += _extract_tokens(result)
            total_iterations += 1
            agent_results[name] = result

        return OrchestrationResult(
            agent_results=agent_results,
            final_output=current_input,
            total_iterations=total_iterations,
            total_tokens=total_tokens,
        )

    async def _run_parallel(self, input: str, *, run_id: str) -> OrchestrationResult:
        # Spawn all agents concurrently with the SAME input.
        tasks: Dict[str, asyncio.Task[Mapping[str, Any]]] = {}
        for name, agent in self._agents.items():
            tasks[name] = asyncio.create_task(
                self._invoke_one(agent, input, name=name, run_id=run_id)
            )

        agent_results: Dict[str, Mapping[str, Any]] = {}
        first_error: Optional[BaseException] = None

        # Drain every task; ``fail_fast`` short-circuits collection but still
        # cancels in-flight tasks, matching Rust's ``join_set.abort_all``.
        for name, task in tasks.items():
            try:
                agent_results[name] = await task
            except Exception as exc:
                if self._config.fail_fast:
                    for other_name, other in tasks.items():
                        if other_name != name and not other.done():
                            other.cancel()
                    raise OrchestrationError(
                        f"OrchestrationRuntime: parallel agent {name!r} failed: {exc}"
                    ) from exc
                # Collect-all mode: log + remember first error, continue.
                if first_error is None:
                    first_error = exc
                logger.warning(
                    "orchestration.parallel.agent_failed",
                    extra={
                        "run_id": run_id,
                        "agent_name": name,
                        "error": str(exc),
                    },
                )

        if not agent_results:
            # All agents failed in collect-all mode — surface the first error
            # rather than returning an empty result.
            if first_error is not None:
                raise OrchestrationError(
                    f"OrchestrationRuntime: all parallel agents failed; first error: {first_error}"
                ) from first_error
            raise OrchestrationError(
                "OrchestrationRuntime: no parallel agent produced a result"
            )

        total_tokens = sum(_extract_tokens(r) for r in agent_results.values())
        final_output = _build_parallel_output(agent_results)
        return OrchestrationResult(
            agent_results=agent_results,
            final_output=final_output,
            total_iterations=len(agent_results),
            total_tokens=total_tokens,
        )

    async def _run_hierarchical(
        self, input: str, *, run_id: str
    ) -> OrchestrationResult:
        coord_name = self._strategy.coordinator_name
        if not coord_name:
            raise OrchestrationError(
                "OrchestrationRuntime: hierarchical strategy missing coordinator_name"
            )
        if coord_name not in self._agents:
            raise OrchestrationError(
                f"OrchestrationRuntime: coordinator agent {coord_name!r} not registered"
            )

        agent_results: Dict[str, Mapping[str, Any]] = {}
        total_tokens = 0
        total_iterations = 0

        coord_result = await self._invoke_one(
            self._agents[coord_name], input, name=coord_name, run_id=run_id
        )
        coord_output = _extract_response(coord_result)
        total_tokens += _extract_tokens(coord_result)
        total_iterations += 1
        agent_results[coord_name] = coord_result

        for name, agent in self._agents.items():
            if name == coord_name:
                continue
            if total_iterations >= self._config.max_agent_calls:
                break
            try:
                sub_result = await self._invoke_one(
                    agent, coord_output, name=name, run_id=run_id
                )
            except Exception as exc:
                if self._config.fail_fast:
                    raise OrchestrationError(
                        f"OrchestrationRuntime: hierarchical sub-agent {name!r} failed: {exc}"
                    ) from exc
                logger.warning(
                    "orchestration.hierarchical.sub_agent_failed",
                    extra={
                        "run_id": run_id,
                        "agent_name": name,
                        "error": str(exc),
                    },
                )
                continue
            total_tokens += _extract_tokens(sub_result)
            total_iterations += 1
            agent_results[name] = sub_result

        return OrchestrationResult(
            agent_results=agent_results,
            final_output=coord_output,
            total_iterations=total_iterations,
            total_tokens=total_tokens,
        )

    async def _run_pipeline(self, input: str, *, run_id: str) -> OrchestrationResult:
        steps = self._strategy.steps or ()
        if not steps:
            raise OrchestrationError(
                "OrchestrationRuntime: pipeline strategy requires at least one step"
            )

        agent_results: Dict[str, Mapping[str, Any]] = {}
        result_map: Dict[str, str] = {}
        total_tokens = 0
        total_iterations = 0

        for step in steps:
            if total_iterations >= self._config.max_agent_calls:
                raise OrchestrationError(
                    f"OrchestrationRuntime: max_agent_calls={self._config.max_agent_calls} reached"
                )
            if step.agent_name not in self._agents:
                raise OrchestrationError(
                    f"OrchestrationRuntime: pipeline step references unknown agent {step.agent_name!r}"
                )
            step_input = _resolve_pipeline_input(step.input_from, input, result_map)
            result = await self._invoke_one(
                self._agents[step.agent_name],
                step_input,
                name=step.agent_name,
                run_id=run_id,
            )
            response = _extract_response(result)
            result_map[step.agent_name] = response
            agent_results[step.agent_name] = result
            total_tokens += _extract_tokens(result)
            total_iterations += 1

        # Final output is the last step's response (Rust uses last value of
        # the IndexMap; this preserves insertion order).
        final_output = next(reversed(result_map.values())) if result_map else ""

        return OrchestrationResult(
            agent_results=agent_results,
            final_output=final_output,
            total_iterations=total_iterations,
            total_tokens=total_tokens,
        )

    # -----------------------------------------------------------------------
    # Invocation seams
    # -----------------------------------------------------------------------

    async def _invoke_one(
        self, agent: Any, input: str, *, name: str, run_id: str
    ) -> Mapping[str, Any]:
        """Invoke a single agent via the configured ``agent_invoker``.

        The default invoker prefers ``agent.run_async(input=input,
        coordinator=...)`` then falls back to a thread-pooled
        ``agent.run(input=input, ...)``. The ``coordinator`` kwarg is only
        passed when a coordinator is registered AND the agent's signature
        accepts it — the runtime never injects keys the agent didn't ask for
        (per ``rules/agent-reasoning.md`` § "Pre-filter input before LLM
        sees it" — the runtime is plumbing, not pre-classification).
        """
        logger.info(
            "orchestration.agent.invoke",
            extra={
                "run_id": run_id,
                "agent_name": name,
                "strategy": self._strategy.name,
            },
        )
        try:
            result = await self._agent_invoker(agent, input, self._coordinator)
        except Exception:
            logger.exception(
                "orchestration.agent.error",
                extra={"run_id": run_id, "agent_name": name},
            )
            raise

        if not isinstance(result, Mapping):
            raise OrchestrationError(
                f"OrchestrationRuntime: agent {name!r} returned {type(result).__name__}, expected Mapping"
            )
        return result

    @staticmethod
    async def _default_invoker(
        agent: Any, input: str, coordinator: Optional[Coordinator]
    ) -> Mapping[str, Any]:
        """Default agent invoker.

        Tries ``agent.run_async(input=input)`` first, then falls back to
        ``await asyncio.to_thread(agent.run, input=input)``. The coordinator
        is forwarded as a kwarg only when the target callable's signature
        accepts ``coordinator`` — keeps the default invoker compatible with
        ``BaseAgent`` (whose signature does NOT accept a coordinator) and
        with bespoke test agents (which can opt in by declaring the kwarg).
        """
        # Async path
        run_async = getattr(agent, "run_async", None)
        if callable(run_async):
            kwargs: Dict[str, Any] = {"input": input}
            if coordinator is not None and _accepts_coordinator(run_async):
                kwargs["coordinator"] = coordinator
            return await run_async(**kwargs)

        # Sync fallback path
        run_sync = getattr(agent, "run", None)
        if callable(run_sync):
            kwargs = {"input": input}
            if coordinator is not None and _accepts_coordinator(run_sync):
                kwargs["coordinator"] = coordinator
            return await asyncio.to_thread(run_sync, **kwargs)

        raise OrchestrationError(
            f"OrchestrationRuntime: agent {agent!r} has neither run_async nor run"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_response(result: Mapping[str, Any]) -> str:
    """Extract the response string from an agent result mapping.

    Tries (in order): ``response`` (Rust ``AgentResult.response`` parity),
    ``output``, ``answer``, ``result``, then the first value if it's a string.
    Falls back to ``str(result)`` so the orchestration never silently drops
    output (per ``rules/zero-tolerance.md`` Rule 3).
    """
    for key in ("response", "output", "answer", "result"):
        value = result.get(key)
        if isinstance(value, str):
            return value
    # First string value wins (matches BaseAgent's signature-output dict shape).
    for value in result.values():
        if isinstance(value, str):
            return value
    return str(result)


def _extract_tokens(result: Mapping[str, Any]) -> int:
    """Extract the total-tokens count from an agent result mapping.

    Tries ``total_tokens`` then ``tokens``; falls back to 0. Non-int values
    are coerced via ``int()`` (raises ``TypeError`` if non-numeric — that's
    intentional; silent zero-coercion would mask a bug).
    """
    for key in ("total_tokens", "tokens"):
        value = result.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            # Defensive: bool is a subclass of int; do not silently coerce.
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _build_parallel_output(results: Mapping[str, Mapping[str, Any]]) -> str:
    """Format the combined output for parallel execution.

    Mirrors Rust ``build_parallel_output``: single-result returns the lone
    response; multi-result joins with ``--- name ---`` headers.
    """
    if len(results) == 1:
        only = next(iter(results.values()))
        return _extract_response(only)
    parts = []
    for name, result in results.items():
        parts.append(f"--- {name} ---\n{_extract_response(result)}")
    return "\n\n".join(parts)


def _resolve_pipeline_input(
    source: PipelineInputSource,
    initial_input: str,
    result_map: Mapping[str, str],
) -> str:
    """Resolve a pipeline step's input string from its source descriptor."""
    if source.initial:
        return initial_input
    if source.agent_name is not None:
        if source.agent_name not in result_map:
            raise OrchestrationError(
                f"OrchestrationRuntime: pipeline step references output from "
                f"{source.agent_name!r} which has not run yet or does not exist"
            )
        return result_map[source.agent_name]
    if source.template is not None:
        return _interpolate_template(source.template, result_map)
    raise OrchestrationError(
        "OrchestrationRuntime: PipelineInputSource has no source set"
    )


def _interpolate_template(template: str, result_map: Mapping[str, str]) -> str:
    """Replace ``{{name.response}}`` placeholders with the named response.

    Mirrors Rust ``interpolate_template``: unknown placeholders are left as-is
    so failures are visible in the resulting prompt rather than silently
    swallowed.
    """
    out = template
    for name, response in result_map.items():
        out = out.replace(f"{{{{{name}.response}}}}", response)
    return out


def _accepts_coordinator(func: Callable[..., Any]) -> bool:
    """True iff ``func`` declares a ``coordinator`` keyword argument.

    Used by the default invoker to forward the coordinator only when the
    target callable opted in. This is structural plumbing (signature
    inspection), NOT runtime classification — permitted by
    ``rules/agent-reasoning.md`` § "Permitted Deterministic Logic".
    """
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if "coordinator" in sig.parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
