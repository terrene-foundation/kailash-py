# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier-1 unit tests for kaizen.orchestration.runtime.OrchestrationRuntime.

Cross-SDK parity test surface — mirrors the Rust
``crates/kaizen-agents/src/orchestration/runtime.rs::tests`` module test
list one-for-one. Every Rust test has a Python equivalent here so the
``OrchestrationRuntime`` shapes stay observably identical (issue #602 /
kailash-rs ISS-27 / EATP D6).

Tests use Protocol-conforming deterministic agents (per ``rules/testing.md``
§ "Protocol Adapters") rather than real LLM agents, so unit runs are
hermetic and fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import pytest

from kaizen.orchestration import (
    OrchestrationConfig,
    OrchestrationError,
    OrchestrationRuntime,
    OrchestrationStrategy,
    OrchestrationStrategyKind,
    PipelineInputSource,
    PipelineStep,
    SharedMemoryCoordinator,
)


# ---------------------------------------------------------------------------
# Test agents
# ---------------------------------------------------------------------------


@dataclass
class _EchoAgent:
    """Minimal Protocol-conforming agent that echoes input with a prefix."""

    name: str
    description: str = ""
    tokens: int = 10

    async def run_async(self, **inputs: Any) -> Mapping[str, Any]:
        text = inputs.get("input", "")
        return {
            "response": f"[{self.name}] {text}",
            "total_tokens": self.tokens,
            "iterations": 1,
        }


@dataclass
class _FailingAgent:
    """Agent that raises on every invocation."""

    name: str

    async def run_async(self, **inputs: Any) -> Mapping[str, Any]:
        raise RuntimeError(f"{self.name} failed intentionally")


@dataclass
class _SlowAgent:
    """Agent that sleeps for ``delay_ms`` before responding."""

    name: str
    delay_ms: int

    async def run_async(self, **inputs: Any) -> Mapping[str, Any]:
        import asyncio

        await asyncio.sleep(self.delay_ms / 1000.0)
        return {"response": f"[{self.name}] slow", "total_tokens": 5}


@dataclass
class _MemoryReaderAgent:
    """Agent that reads ``key`` from the coordinator and reports it."""

    name: str
    key: str

    async def run_async(
        self, *, input: str = "", coordinator: Optional[Any] = None
    ) -> Mapping[str, Any]:
        if coordinator is None:
            return {"response": f"{self.key}=<no coordinator>", "total_tokens": 1}
        value = await coordinator.retrieve(self.key)
        if value is None:
            return {"response": f"{self.key}=<not found>", "total_tokens": 1}
        return {"response": f"{self.key}={value}", "total_tokens": 1}


@dataclass
class _MemoryWriterAgent:
    """Agent that writes ``(key, value)`` to the coordinator."""

    name: str
    key: str
    value: str

    async def run_async(
        self, *, input: str = "", coordinator: Optional[Any] = None
    ) -> Mapping[str, Any]:
        if coordinator is not None:
            await coordinator.store(self.key, self.value)
        return {"response": f"stored {self.key}={self.value}", "total_tokens": 1}


# ---------------------------------------------------------------------------
# Builder API
# ---------------------------------------------------------------------------


class TestBuilder:
    def test_new_creates_empty_runtime(self) -> None:
        runtime = OrchestrationRuntime()
        assert runtime.agent_count == 0
        assert runtime.agent_names == []
        assert runtime.current_strategy.kind is OrchestrationStrategyKind.SEQUENTIAL
        assert runtime.current_coordinator is None

    def test_add_agent_increases_count(self) -> None:
        runtime = (
            OrchestrationRuntime()
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
        )
        assert runtime.agent_count == 2
        assert runtime.agent_names == ["a", "b"]

    def test_add_agent_preserves_insertion_order(self) -> None:
        runtime = (
            OrchestrationRuntime()
            .add_agent("z", _EchoAgent("z"))
            .add_agent("a", _EchoAgent("a"))
            .add_agent("m", _EchoAgent("m"))
        )
        assert runtime.agent_names == ["z", "a", "m"]

    def test_add_agent_duplicate_name_replaces(self) -> None:
        runtime = (
            OrchestrationRuntime()
            .add_agent("a", _EchoAgent("a1"))
            .add_agent("a", _EchoAgent("a2"))
        )
        assert runtime.agent_count == 1

    def test_add_agent_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty name"):
            OrchestrationRuntime().add_agent("", _EchoAgent("a"))

    def test_strategy_setter(self) -> None:
        runtime = OrchestrationRuntime().strategy(OrchestrationStrategy.parallel())
        assert runtime.current_strategy.kind is OrchestrationStrategyKind.PARALLEL

    def test_strategy_setter_rejects_none(self) -> None:
        with pytest.raises(ValueError, match="non-None strategy"):
            OrchestrationRuntime().strategy(None)  # type: ignore[arg-type]

    def test_config_setter(self) -> None:
        cfg = OrchestrationConfig(
            max_total_iterations=10,
            max_agent_calls=20,
            timeout_secs=60.0,
            fail_fast=False,
            share_conversation_history=True,
        )
        runtime = OrchestrationRuntime().config(cfg)
        assert runtime.current_config.max_total_iterations == 10
        assert runtime.current_config.fail_fast is False

    def test_config_setter_rejects_none(self) -> None:
        with pytest.raises(ValueError, match="non-None config"):
            OrchestrationRuntime().config(None)  # type: ignore[arg-type]

    def test_default_config_values(self) -> None:
        cfg = OrchestrationConfig()
        assert cfg.max_total_iterations == 50
        assert cfg.max_agent_calls == 100
        assert cfg.timeout_secs is None
        assert cfg.fail_fast is True
        assert cfg.share_conversation_history is False

    def test_coordinator_setter(self) -> None:
        coord = SharedMemoryCoordinator()
        runtime = OrchestrationRuntime().coordinator(coord)
        assert runtime.current_coordinator is coord

    def test_coordinator_setter_accepts_none(self) -> None:
        runtime = OrchestrationRuntime().coordinator(None)
        assert runtime.current_coordinator is None


# ---------------------------------------------------------------------------
# Strategy enum
# ---------------------------------------------------------------------------


class TestStrategy:
    def test_strategy_names(self) -> None:
        assert OrchestrationStrategy.sequential().name == "sequential"
        assert OrchestrationStrategy.parallel().name == "parallel"
        assert OrchestrationStrategy.hierarchical("coord").name == "hierarchical"
        assert (
            OrchestrationStrategy.pipeline(
                [PipelineStep("a", PipelineInputSource.from_initial())]
            ).name
            == "pipeline"
        )

    def test_hierarchical_requires_coordinator_name(self) -> None:
        with pytest.raises(ValueError, match="coordinator_name"):
            OrchestrationStrategy.hierarchical("")

    def test_pipeline_requires_steps(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            OrchestrationStrategy.pipeline([])

    def test_pipeline_input_source_factories(self) -> None:
        a = PipelineInputSource.from_initial()
        assert a.initial is True

        b = PipelineInputSource.from_agent_output("upstream")
        assert b.agent_name == "upstream"

        c = PipelineInputSource.from_template("Summarize: {{x.response}}")
        assert c.template == "Summarize: {{x.response}}"

    def test_pipeline_input_source_validation(self) -> None:
        with pytest.raises(ValueError):
            PipelineInputSource.from_agent_output("")
        with pytest.raises(ValueError):
            PipelineInputSource.from_template(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Run errors
# ---------------------------------------------------------------------------


class TestRunErrors:
    @pytest.mark.asyncio
    async def test_run_empty_runtime_raises(self) -> None:
        runtime = OrchestrationRuntime()
        with pytest.raises(OrchestrationError, match="no agents registered"):
            await runtime.run("hello")

    @pytest.mark.asyncio
    async def test_hierarchical_missing_coordinator_raises(self) -> None:
        runtime = OrchestrationRuntime(
            strategy=OrchestrationStrategy.hierarchical("nonexistent")
        ).add_agent("worker", _EchoAgent("worker"))
        with pytest.raises(OrchestrationError, match="coordinator agent"):
            await runtime.run("test")

    @pytest.mark.asyncio
    async def test_pipeline_missing_agent_raises(self) -> None:
        runtime = OrchestrationRuntime(
            strategy=OrchestrationStrategy.pipeline(
                [PipelineStep("nonexistent", PipelineInputSource.from_initial())]
            )
        ).add_agent("a", _EchoAgent("a"))
        with pytest.raises(OrchestrationError, match="unknown agent"):
            await runtime.run("test")

    @pytest.mark.asyncio
    async def test_pipeline_agent_output_unresolved_raises(self) -> None:
        # Step 1 references the OUTPUT of "a" but "a" has not run yet.
        runtime = (
            OrchestrationRuntime(
                strategy=OrchestrationStrategy.pipeline(
                    [
                        PipelineStep(
                            "b",
                            PipelineInputSource.from_agent_output("a"),
                        ),
                    ]
                )
            )
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
        )
        with pytest.raises(OrchestrationError, match="has not run"):
            await runtime.run("test")


# ---------------------------------------------------------------------------
# Sequential
# ---------------------------------------------------------------------------


class TestSequential:
    @pytest.mark.asyncio
    async def test_sequential_single_agent(self) -> None:
        runtime = OrchestrationRuntime().add_agent("echo", _EchoAgent("echo"))
        result = await runtime.run("hello")
        assert result.final_output == "[echo] hello"
        assert "echo" in result.agent_results
        assert result.total_iterations == 1
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_sequential_chains_output(self) -> None:
        runtime = (
            OrchestrationRuntime()
            .add_agent("researcher", _EchoAgent("researcher"))
            .add_agent("writer", _EchoAgent("writer"))
        )
        result = await runtime.run("topic")
        assert result.final_output == "[writer] [researcher] topic"
        assert result.total_iterations == 2
        assert result.total_tokens == 20  # 10 per agent

    @pytest.mark.asyncio
    async def test_sequential_three_agents(self) -> None:
        runtime = (
            OrchestrationRuntime()
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
            .add_agent("c", _EchoAgent("c"))
        )
        result = await runtime.run("input")
        assert result.final_output == "[c] [b] [a] input"
        assert result.total_iterations == 3


# ---------------------------------------------------------------------------
# Parallel
# ---------------------------------------------------------------------------


class TestParallel:
    @pytest.mark.asyncio
    async def test_parallel_all_agents_receive_same_input(self) -> None:
        runtime = (
            OrchestrationRuntime(strategy=OrchestrationStrategy.parallel())
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
        )
        result = await runtime.run("hello")
        assert result.agent_results["a"]["response"] == "[a] hello"
        assert result.agent_results["b"]["response"] == "[b] hello"

    @pytest.mark.asyncio
    async def test_parallel_aggregates_tokens(self) -> None:
        runtime = (
            OrchestrationRuntime(strategy=OrchestrationStrategy.parallel())
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
            .add_agent("c", _EchoAgent("c"))
        )
        result = await runtime.run("test")
        assert result.total_tokens == 30  # 10 per agent

    @pytest.mark.asyncio
    async def test_parallel_fail_fast_propagates_error(self) -> None:
        runtime = (
            OrchestrationRuntime(
                strategy=OrchestrationStrategy.parallel(),
                config=OrchestrationConfig(fail_fast=True),
            )
            .add_agent("ok", _EchoAgent("ok"))
            .add_agent("fail", _FailingAgent("fail"))
        )
        with pytest.raises(OrchestrationError, match="parallel agent"):
            await runtime.run("test")

    @pytest.mark.asyncio
    async def test_parallel_no_fail_fast_collects_successes(self) -> None:
        runtime = (
            OrchestrationRuntime(
                strategy=OrchestrationStrategy.parallel(),
                config=OrchestrationConfig(fail_fast=False),
            )
            .add_agent("ok", _EchoAgent("ok"))
            .add_agent("fail", _FailingAgent("fail"))
        )
        result = await runtime.run("test")
        assert "ok" in result.agent_results
        assert "fail" not in result.agent_results

    @pytest.mark.asyncio
    async def test_parallel_single_agent_unwrapped_output(self) -> None:
        runtime = OrchestrationRuntime(
            strategy=OrchestrationStrategy.parallel()
        ).add_agent("solo", _EchoAgent("solo"))
        result = await runtime.run("hi")
        # Single-result form: lone response, no header decoration.
        assert result.final_output == "[solo] hi"

    @pytest.mark.asyncio
    async def test_parallel_multi_agent_headered_output(self) -> None:
        runtime = (
            OrchestrationRuntime(strategy=OrchestrationStrategy.parallel())
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
        )
        result = await runtime.run("hi")
        assert "--- a ---" in result.final_output
        assert "[a] hi" in result.final_output
        assert "--- b ---" in result.final_output
        assert "[b] hi" in result.final_output


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_basic(self) -> None:
        runtime = (
            OrchestrationRuntime(
                strategy=OrchestrationStrategy.pipeline(
                    [
                        PipelineStep("a", PipelineInputSource.from_initial()),
                        PipelineStep(
                            "b",
                            PipelineInputSource.from_agent_output("a"),
                        ),
                    ]
                )
            )
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
        )
        result = await runtime.run("start")
        assert result.final_output == "[b] [a] start"

    @pytest.mark.asyncio
    async def test_pipeline_with_template(self) -> None:
        runtime = (
            OrchestrationRuntime(
                strategy=OrchestrationStrategy.pipeline(
                    [
                        PipelineStep("a", PipelineInputSource.from_initial()),
                        PipelineStep(
                            "b",
                            PipelineInputSource.from_template(
                                "Summarize: {{a.response}}"
                            ),
                        ),
                    ]
                )
            )
            .add_agent("a", _EchoAgent("a"))
            .add_agent("b", _EchoAgent("b"))
        )
        result = await runtime.run("research topic")
        assert result.final_output == "[b] Summarize: [a] research topic"


# ---------------------------------------------------------------------------
# Hierarchical
# ---------------------------------------------------------------------------


class TestHierarchical:
    @pytest.mark.asyncio
    async def test_hierarchical_runs_coordinator_then_workers(self) -> None:
        runtime = (
            OrchestrationRuntime(strategy=OrchestrationStrategy.hierarchical("coord"))
            .add_agent("coord", _EchoAgent("coord"))
            .add_agent("worker_a", _EchoAgent("worker_a"))
            .add_agent("worker_b", _EchoAgent("worker_b"))
        )
        result = await runtime.run("plan")
        assert result.total_iterations == 3
        # Final output is the coordinator's response (the "synthesis").
        assert result.final_output == "[coord] plan"
        # Both workers received the coordinator's output as input.
        assert result.agent_results["worker_a"]["response"] == "[worker_a] [coord] plan"
        assert result.agent_results["worker_b"]["response"] == "[worker_b] [coord] plan"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    @pytest.mark.asyncio
    async def test_run_with_timeout_succeeds_when_fast_enough(self) -> None:
        runtime = OrchestrationRuntime(
            config=OrchestrationConfig(timeout_secs=5.0),
        ).add_agent("fast", _SlowAgent("fast", delay_ms=10))
        result = await runtime.run("test")
        assert result.final_output == "[fast] slow"

    @pytest.mark.asyncio
    async def test_run_with_timeout_fails_when_too_slow(self) -> None:
        import asyncio

        runtime = OrchestrationRuntime(
            config=OrchestrationConfig(timeout_secs=0.05),
        ).add_agent("slow", _SlowAgent("slow", delay_ms=2000))
        with pytest.raises(asyncio.TimeoutError):
            await runtime.run("test")


# ---------------------------------------------------------------------------
# Coordinator integration (Tier-1 — uses default in-memory coordinator)
# ---------------------------------------------------------------------------


class TestCoordinator:
    @pytest.mark.asyncio
    async def test_sequential_with_coordinator(self) -> None:
        coord = SharedMemoryCoordinator()
        runtime = (
            OrchestrationRuntime(coordinator=coord)
            .add_agent("writer", _MemoryWriterAgent("writer", "research", "findings"))
            .add_agent("reader", _MemoryReaderAgent("reader", "research"))
        )
        result = await runtime.run("start")
        assert result.final_output == "research=findings"

    @pytest.mark.asyncio
    async def test_no_coordinator_means_isolated_agents(self) -> None:
        # No coordinator passed — the reader sees `<no coordinator>`.
        runtime = (
            OrchestrationRuntime()
            .add_agent("writer", _MemoryWriterAgent("writer", "research", "findings"))
            .add_agent("reader", _MemoryReaderAgent("reader", "research"))
        )
        result = await runtime.run("start")
        assert result.final_output == "research=<no coordinator>"


# ---------------------------------------------------------------------------
# Sync convenience
# ---------------------------------------------------------------------------


class TestRunSync:
    def test_run_sync_executes_outside_event_loop(self) -> None:
        runtime = OrchestrationRuntime().add_agent("echo", _EchoAgent("echo"))
        result = runtime.run_sync("hi")
        assert result.final_output == "[echo] hi"
