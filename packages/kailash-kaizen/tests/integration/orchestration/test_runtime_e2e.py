# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier-2 end-to-end integration tests for kaizen.orchestration.OrchestrationRuntime.

Per ``rules/testing.md`` § "Protocol Adapters", a deterministic
Protocol-conforming agent + the real ``SharedMemoryPool``-backed coordinator
are an acceptable Tier-2 surface for transport-only modules. The runtime
contains zero LLM calls and zero external infrastructure — its full
contract is exercised end-to-end through the public ``run`` entry point with
the default invoker, the real coordinator, and multi-strategy compositions.

For LLM-driven coverage of the same surface, see Tier-3 e2e suites that
plug live ``BaseAgent`` instances into this runtime — out of scope for the
runtime's parity tests.

Mirrors the Rust ``orchestration::runtime::tests`` shared-memory and
multi-strategy integration tests one-for-one (issue #602 / EATP D6).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import pytest

from kaizen.orchestration import (
    OrchestrationConfig,
    OrchestrationRuntime,
    OrchestrationStrategy,
    PipelineInputSource,
    PipelineStep,
    SharedMemoryCoordinator,
)


# ---------------------------------------------------------------------------
# Real coordinator-aware agents
# ---------------------------------------------------------------------------


@dataclass
class _StoreAgent:
    name: str
    key: str
    value: str

    async def run_async(
        self, *, input: str = "", coordinator: Optional[Any] = None
    ) -> Mapping[str, Any]:
        if coordinator is None:
            raise RuntimeError(f"{self.name}: coordinator required")
        await coordinator.store(self.key, self.value)
        return {
            "response": f"stored {self.key}",
            "total_tokens": 5,
        }


@dataclass
class _LoadAgent:
    name: str
    key: str

    async def run_async(
        self, *, input: str = "", coordinator: Optional[Any] = None
    ) -> Mapping[str, Any]:
        if coordinator is None:
            raise RuntimeError(f"{self.name}: coordinator required")
        value = await coordinator.retrieve(self.key)
        return {"response": str(value), "total_tokens": 5}


@dataclass
class _UppercaseAgent:
    name: str

    async def run_async(self, **inputs: Any) -> Mapping[str, Any]:
        text = inputs.get("input", "")
        return {"response": text.upper(), "total_tokens": 7}


@dataclass
class _ReverseAgent:
    name: str

    async def run_async(self, **inputs: Any) -> Mapping[str, Any]:
        text = inputs.get("input", "")
        return {"response": text[::-1], "total_tokens": 7}


# ---------------------------------------------------------------------------
# End-to-end pipelines
# ---------------------------------------------------------------------------


class TestRuntimeEndToEnd:
    @pytest.mark.asyncio
    async def test_sequential_with_real_shared_memory(self) -> None:
        """Writer -> Reader through the real SharedMemoryPool-backed coordinator."""
        coord = SharedMemoryCoordinator()
        runtime = (
            OrchestrationRuntime(coordinator=coord)
            .add_agent("store", _StoreAgent("store", "research", "Q3 trend"))
            .add_agent("load", _LoadAgent("load", "research"))
        )
        result = await runtime.run("seed")
        # The reader's view of shared memory IS the final output.
        assert result.final_output == "Q3 trend"
        # Both agents executed; total_iterations covers them.
        assert result.total_iterations == 2

    @pytest.mark.asyncio
    async def test_pipeline_template_chains_two_real_transformations(self) -> None:
        """Pipeline with a real Template step chaining two transformations."""
        runtime = (
            OrchestrationRuntime(
                strategy=OrchestrationStrategy.pipeline(
                    [
                        PipelineStep("upper", PipelineInputSource.from_initial()),
                        PipelineStep(
                            "reverse",
                            PipelineInputSource.from_template(
                                "transform: {{upper.response}}"
                            ),
                        ),
                    ]
                )
            )
            .add_agent("upper", _UppercaseAgent("upper"))
            .add_agent("reverse", _ReverseAgent("reverse"))
        )
        result = await runtime.run("hello world")
        # upper("hello world") -> "HELLO WORLD"
        # template -> "transform: HELLO WORLD"
        # reverse(template) -> reversed string
        assert result.final_output == "transform: HELLO WORLD"[::-1]

    @pytest.mark.asyncio
    async def test_parallel_aggregates_real_responses(self) -> None:
        runtime = (
            OrchestrationRuntime(strategy=OrchestrationStrategy.parallel())
            .add_agent("upper", _UppercaseAgent("upper"))
            .add_agent("reverse", _ReverseAgent("reverse"))
        )
        result = await runtime.run("kaizen")
        assert result.agent_results["upper"]["response"] == "KAIZEN"
        assert result.agent_results["reverse"]["response"] == "neziak"
        assert "--- upper ---" in result.final_output
        assert "--- reverse ---" in result.final_output

    @pytest.mark.asyncio
    async def test_hierarchical_with_real_workers(self) -> None:
        runtime = (
            OrchestrationRuntime(strategy=OrchestrationStrategy.hierarchical("upper"))
            .add_agent("upper", _UppercaseAgent("upper"))
            .add_agent("reverse", _ReverseAgent("reverse"))
        )
        result = await runtime.run("kaizen")
        # Coordinator runs first → "KAIZEN"
        assert result.final_output == "KAIZEN"
        # Worker receives the coordinator's output → reverse("KAIZEN")
        assert result.agent_results["reverse"]["response"] == "NEZIAK"

    @pytest.mark.asyncio
    async def test_max_agent_calls_caps_sequential(self) -> None:
        from kaizen.orchestration import OrchestrationError

        runtime = (
            OrchestrationRuntime(
                config=OrchestrationConfig(max_agent_calls=1),
            )
            .add_agent("a", _UppercaseAgent("a"))
            .add_agent("b", _UppercaseAgent("b"))
        )
        with pytest.raises(OrchestrationError, match="max_agent_calls"):
            await runtime.run("x")

    @pytest.mark.asyncio
    async def test_run_emits_duration_ms(self) -> None:
        runtime = OrchestrationRuntime().add_agent("u", _UppercaseAgent("u"))
        result = await runtime.run("x")
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# Cross-SDK shape parity (kailash-rs ISS-27 — observable contract test)
# ---------------------------------------------------------------------------


class TestCrossSdkShapeParity:
    """Observable-shape parity with kailash-rs `OrchestrationResult`.

    These assertions lock the field shape of OrchestrationResult so a future
    refactor cannot rename / drop a field that the Rust SDK also emits. EATP
    D6 mandates semantic parity; these tests are the structural defense.
    """

    @pytest.mark.asyncio
    async def test_result_field_shape(self) -> None:
        runtime = OrchestrationRuntime().add_agent("u", _UppercaseAgent("u"))
        result = await runtime.run("hi")
        d = result.to_dict()
        # Same five keys as the Rust struct.
        assert set(d.keys()) == {
            "agent_results",
            "final_output",
            "total_iterations",
            "total_tokens",
            "duration_ms",
        }
        assert isinstance(d["agent_results"], dict)
        assert isinstance(d["final_output"], str)
        assert isinstance(d["total_iterations"], int)
        assert isinstance(d["total_tokens"], int)
        assert isinstance(d["duration_ms"], int)

    @pytest.mark.asyncio
    async def test_strategy_kind_round_trips_via_string_value(self) -> None:
        # Cross-SDK serde: Rust serializes the strategy enum as a string
        # variant. Python's StrEnum yields the same lowercase value.
        assert OrchestrationStrategy.sequential().kind.value == "sequential"
        assert OrchestrationStrategy.parallel().kind.value == "parallel"
        assert OrchestrationStrategy.hierarchical("c").kind.value == "hierarchical"
        assert (
            OrchestrationStrategy.pipeline(
                [PipelineStep("a", PipelineInputSource.from_initial())]
            ).kind.value
            == "pipeline"
        )
