"""Regression: OrchestrationRuntime conveyed NO task to its agent nodes (#1720).

``OrchestrationRuntime._build_workflow_from_agents`` configured every agent's
``LLMAgentNode`` with ``{"agent": agent, "task": task, "provider": ..., "model":
...}``. Neither ``agent`` nor ``task`` is a declared ``LLMAgentNode``
parameter, so the Kailash runtime dropped both with only::

    WARNING [NODE] Unknown parameter(s) for LLMAgentNode: ['agent', 'task']

and the node then ran with ``messages=[]`` — an LLM call carrying no
instruction at all. The call still returned ``success: True`` with fabricated
content, so ``execute_multi_agent_workflow`` counted it ``completed`` and
reported ``success_rate == 1.0`` for a workflow that never conveyed any work.
That is ``rules/zero-tolerance.md`` Rule 2 "fake integration via a missing
handoff field", in its worst variant: not "returns nothing" but "returns
something plausible and wrong".

Three further defects lived in the same function:

* ``provider`` fell back to a hardcoded ``"openai"`` guarded by
  ``hasattr(agent.config, "provider")`` — but ``BaseAgentConfig`` exposes
  ``llm_provider``, never ``provider``, so the probe was ALWAYS False and every
  agent was forced onto ``"openai"`` regardless of its configuration.
* ``model`` fell back to a hardcoded ``"gpt-4o-mini"`` literal, BLOCKED by
  ``rules/env-models.md``.
* ``mode="hybrid"`` was documented as "batch parallelism" but implemented only
  as a comment, so it silently aliased ``"parallel"``; ``mode="sequential"``
  called ``add_connection`` with the wrong argument order and raised
  ``WorkflowValidationError`` on every use since introduction.

These tests assert the CONFIG the builder produces, so a refactor that drops
the task, reintroduces a literal provider/model, or re-adds an undeclared
parameter fails loudly here rather than silently shipping empty LLM calls.
"""

from __future__ import annotations

import logging

import pytest
from kailash.nodes.base import NodeRegistry
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen_agents.patterns.runtime import (
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
)

pytestmark = pytest.mark.regression

TASK_A = "Summarize the Q3 revenue report for the board"
TASK_B = "Draft a customer apology email about the outage"


def _agent(agent_id: str, **config_kwargs) -> BaseAgent:
    """A BaseAgent whose provider is the explicitly-requested mock provider."""
    config_kwargs.setdefault("llm_provider", "mock")
    return BaseAgent(agent_id=agent_id, config=BaseAgentConfig(**config_kwargs))


@pytest.fixture
def runtime() -> OrchestrationRuntime:
    return OrchestrationRuntime(
        config=OrchestrationRuntimeConfig(
            max_concurrent_agents=3, enable_health_monitoring=False
        )
    )


def _node_configs(workflow) -> list[dict]:
    return [spec["config"] for spec in workflow.nodes.values()]


# ---------------------------------------------------------------------------
# The load-bearing assertion: the task reaches the node.
# ---------------------------------------------------------------------------


def test_built_node_config_carries_the_task_as_openai_messages(runtime):
    """THE regression: each node's config MUST convey its own task.

    Reverting the fix (restoring ``"task": task``) leaves ``messages`` absent,
    and this fails on the first assertion.
    """
    workflow = runtime._build_workflow_from_agents(
        [_agent("alpha"), _agent("beta")], [TASK_A, TASK_B], mode="parallel"
    )

    configs = _node_configs(workflow)
    assert len(configs) == 2

    for config, expected_task in zip(configs, [TASK_A, TASK_B], strict=True):
        assert "messages" in config, (
            "node config carries no 'messages' — the agent would run with an "
            "empty conversation and never be told its task (#1720)"
        )
        assert config["messages"] == [{"role": "user", "content": expected_task}], (
            "task MUST be conveyed as an OpenAI-format user turn, the shape "
            "LLMAgentNode.get_parameters() declares for 'messages'"
        )


def test_task_is_not_passed_as_an_undeclared_node_parameter(runtime):
    """``agent``/``task`` are not LLMAgentNode parameters and MUST NOT appear."""
    workflow = runtime._build_workflow_from_agents(
        [_agent("alpha")], [TASK_A], mode="parallel"
    )
    config = _node_configs(workflow)[0]

    assert "task" not in config, (
        "'task' is not a declared LLMAgentNode parameter — the runtime drops "
        "it with a WARNING and the node runs with no instruction (#1720)"
    )
    assert "agent" not in config, (
        "'agent' is not a declared LLMAgentNode parameter (and a BaseAgent is "
        "not serializable into a node config)"
    )


def test_every_config_key_is_a_declared_llm_agent_node_parameter(runtime):
    """Structural guard: catches ANY future undeclared key, not just these two.

    Derived from the live node contract rather than a hardcoded list, so the
    guard tracks ``LLMAgentNode.get_parameters()`` as it evolves.
    """
    declared = set(NodeRegistry.get("LLMAgentNode")().get_parameters())
    assert {
        "messages",
        "provider",
        "model",
        "system_prompt",
    } <= declared, "node contract changed shape; this regression test needs revisiting"

    workflow = runtime._build_workflow_from_agents(
        [_agent("alpha", model="pinned-model")], [TASK_A], mode="parallel"
    )
    undeclared = set(_node_configs(workflow)[0]) - declared
    assert not undeclared, (
        f"node config carries undeclared parameter(s) {sorted(undeclared)}; "
        "the Kailash runtime drops these silently with only a WARNING"
    )


def test_node_validation_emits_no_unknown_parameter_warning(runtime, caplog):
    """The runtime's own 'Unknown parameter(s)' WARNING MUST NOT fire.

    That warning was the ONLY signal the handoff was broken, so it is asserted
    on the real path that emits it: ``Node.validate_inputs()``, which
    ``Node.execute()`` calls with the merged config
    (``src/kailash/nodes/base.py``). Any key the node does not declare is
    dropped there with a WARNING and never reaches ``run()``.
    """
    workflow = runtime._build_workflow_from_agents(
        [_agent("alpha"), _agent("beta")], [TASK_A, TASK_B], mode="parallel"
    )
    assert workflow.build() is not None

    node_cls = NodeRegistry.get("LLMAgentNode")
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        for node_id, spec in workflow.nodes.items():
            validated = node_cls(name=node_id).validate_inputs(**spec["config"])
            assert validated.get("messages"), (
                f"node {node_id!r} passed validation with no conversation — "
                "the LLM would be called with no instruction (#1720)"
            )

    offending = [
        record.getMessage()
        for record in caplog.records
        if "Unknown parameter" in record.getMessage()
    ]
    assert not offending, "the runtime dropped node parameters:\n" + "\n".join(
        offending
    )


def test_undeclared_parameters_are_dropped_silently_enough_to_need_the_guard():
    """Pins WHY the guard above matters: an undeclared key only WARNs.

    ``validate_inputs`` returns successfully with the key removed, so a caller
    relying on it sees nothing (``rules/zero-tolerance.md`` Rule 3 — the
    framework's drop-with-a-WARNING is not something a caller may lean on).
    """
    node = NodeRegistry.get("LLMAgentNode")(name="probe")
    validated = node.validate_inputs(
        provider="mock", model="m", messages=[], task="the task", agent=object()
    )
    assert (
        "task" not in validated and "agent" not in validated
    ), "LLMAgentNode began accepting 'task'/'agent'; #1720's premise changed"


# ---------------------------------------------------------------------------
# provider / model: no hardcoded identifiers (rules/env-models.md)
# ---------------------------------------------------------------------------


def test_provider_comes_from_agent_config_not_a_hardcoded_literal(runtime):
    """``BaseAgentConfig`` exposes ``llm_provider``; a literal must not win.

    The old ``hasattr(agent.config, "provider")`` probe was always False, so
    every agent — however configured — was forced onto ``"openai"``.
    """
    assert not hasattr(BaseAgentConfig(), "provider"), (
        "BaseAgentConfig grew a 'provider' attribute; the #1720 mis-probe "
        "rationale needs revisiting"
    )

    workflow = runtime._build_workflow_from_agents(
        [_agent("alpha", llm_provider="mock")], [TASK_A], mode="parallel"
    )
    assert _node_configs(workflow)[0]["provider"] == "mock", (
        "the agent's configured provider was overridden — a wrong-provider "
        "guess routes the call to the wrong vendor entirely (#1720)"
    )


def test_model_is_never_a_hardcoded_literal(runtime):
    """A configured model is honoured; an unset one defers to the node.

    ``LLMAgentNode`` declares its own env-driven default
    (``OPENAI_PROD_MODEL`` -> ``DEFAULT_LLM_MODEL`` -> the provider-intrinsic
    named constant), so omitting the key is how the builder stays free of
    model literals.
    """
    configured = _node_configs(
        runtime._build_workflow_from_agents(
            [_agent("alpha", model="pinned-model")], [TASK_A], mode="parallel"
        )
    )[0]
    assert configured["model"] == "pinned-model"

    unset = _node_configs(
        runtime._build_workflow_from_agents(
            [_agent("beta", model=None)], [TASK_B], mode="parallel"
        )
    )[0]
    assert "model" not in unset, (
        "builder injected a model for an agent that configured none — it MUST "
        "defer to LLMAgentNode's env-resolved default, never a literal "
        "(rules/env-models.md)"
    )


def test_agent_config_fields_reach_the_node(runtime):
    """The mapping reuses ``BaseAgent.to_workflow()``, so config survives.

    The old inline mapping dropped system_prompt, temperature, max_tokens,
    response_format and the governance opt-out entirely.
    """
    config = _node_configs(
        runtime._build_workflow_from_agents(
            [_agent("alpha", temperature=0.25, max_tokens=321)],
            [TASK_A],
            mode="parallel",
        )
    )[0]

    assert config["generation_config"]["temperature"] == 0.25
    assert config["generation_config"]["max_tokens"] == 321
    assert config.get(
        "system_prompt"
    ), "the agent's signature-derived system prompt never reached the node"


# ---------------------------------------------------------------------------
# mode: no silent aliasing, no silently-broken path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["hybrid", "sequential", "squential", ""])
def test_unsupported_mode_raises_naming_the_supported_modes(runtime, mode):
    """``hybrid`` silently aliased parallel; ``sequential`` was always broken."""
    with pytest.raises(ValueError, match=r"Unsupported workflow build mode"):
        runtime._build_workflow_from_agents([_agent("alpha")], [TASK_A], mode=mode)

    with pytest.raises(ValueError, match=r"parallel"):
        runtime._build_workflow_from_agents([_agent("alpha")], [TASK_A], mode=mode)


def test_parallel_mode_adds_no_connections(runtime):
    """Level-based concurrency depends on the nodes being independent."""
    workflow = runtime._build_workflow_from_agents(
        [_agent("alpha"), _agent("beta")], [TASK_A, TASK_B], mode="parallel"
    )
    assert workflow.connections == []


def test_agent_without_to_workflow_raises_typed_error(runtime):
    """A non-BaseAgent gets a named error, not an opaque AttributeError.

    ``kaizen.core.agents.Agent`` is a separate hierarchy exposing
    ``compile_to_workflow()``; letting ``None.to_workflow`` style access
    propagate would violate ``rules/zero-tolerance.md`` Rule 3a.
    """

    class NotAnAgent:
        agent_id = "impostor"

    with pytest.raises(TypeError, match=r"does not expose to_workflow"):
        runtime._build_workflow_from_agents([NotAnAgent()], [TASK_A], mode="parallel")


# ---------------------------------------------------------------------------
# End-to-end: the task is observable in what the LLM actually received.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_agent_workflow_conveys_the_task_end_to_end():
    """The deterministic mock provider echoes its last user turn.

    Its content is therefore direct evidence of what the node sent. Before the
    fix the node received ``messages=[]``, so the echo was ``'...'`` — an
    empty task presented as a completed one.
    """
    runtime = OrchestrationRuntime(
        config=OrchestrationRuntimeConfig(
            max_concurrent_agents=2, enable_health_monitoring=False
        )
    )
    await runtime.start()
    try:
        await runtime.register_agent(_agent("worker_001"), max_concurrency=1)

        results = await runtime.execute_multi_agent_workflow(
            tasks=[TASK_B], routing_strategy="round-robin", error_handling="graceful"
        )

        assert results["completed_tasks"] == 1, results
        content = results["results"][0]["result"]["response"]["content"]
        assert TASK_B in content, (
            "the task text never reached the LLM: the provider echoed "
            f"{content!r}. A 'completed' task whose prompt was empty is the "
            "#1720 fake-integration shape."
        )
    finally:
        await runtime.shutdown(graceful=False)
