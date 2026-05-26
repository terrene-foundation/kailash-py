# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for ``Workflow.from_brief()`` — issue #1125 AC 6.

These tests hit a real LLM endpoint via :func:`os.environ`-configured
``DEFAULT_LLM_MODEL`` per ``rules/env-models.md`` and ``rules/testing.md``
§ "Tier 2 (Integration): Real infrastructure recommended" — NO MOCKING.
Per ``rules/testing.md`` § "End-to-End Pipeline Regression Above Unit +
Integration", every canonical pipeline the docs teach MUST have a Tier-2+
regression test executing DOCS-EXACT code against real infra; this file
is the regression surface for the issue #1125 AC 1 documented call
``Workflow.from_brief(brief)``.

Probe shape: the tests assert STRUCTURAL properties (per
``rules/probe-driven-verification.md`` Rule 3 — structural probes when
LLM-judge is unavailable in CI):

- `isinstance(result, WorkflowBuilder)` — return-type contract.
- `result.build()` returns a `Workflow` without raising — graph
  validity contract.
- `len(workflow.nodes) >= expected_min_nodes` — plan size shape.
- For error-path: `BriefInterpretationError` raised with typed
  discriminator (`low_confidence=True` OR `unknown_value` set).

The tests intentionally do NOT regex-match the LLM's prose (per
``rules/probe-driven-verification.md`` MUST-1 — semantic verification
MUST be probe-driven, not regex/keyword); they assert SHAPE, not exact
node names. Three brief shapes cover AC 6: simple linear, branching,
error-path.

CI cost note (per ``rules/testing.md`` § "CI cost surfacing for human
gate"): each test invokes one LLM completion against
``DEFAULT_LLM_MODEL``. Typical per-PR run cost across 3 tests: ~3 LLM
completions at the cheapest small-model tier (e.g. gpt-4o-mini-class
spend in the cents range). Tests SKIP cleanly when DEFAULT_LLM_MODEL
or the matched API key is unset.

Origin: issue #1125 AC 6 — Tier-2 tests covering ≥3 brief shapes
without mocking. Sibling shards (S3 kailash-dataflow, S4 kaizen)
land their primitive's Tier-2 surface independently.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

# Marker pair per the shard plan: @pytest.mark.regression for tracking,
# @pytest.mark.integration for the no-mocking discipline gate.
pytestmark = [pytest.mark.regression, pytest.mark.integration]


FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "regression"
    / "from_brief"
    / "fixtures"
)


def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a YAML fixture from the from_brief regression fixture dir.

    Args:
        name: Filename relative to :data:`FIXTURE_DIR` (e.g.
            ``"workflow_linear.yaml"``).

    Returns:
        The parsed YAML dict.
    """
    path = FIXTURE_DIR / name
    return yaml.safe_load(path.read_text())


def _has_llm_env() -> bool:
    """Return ``True`` when the required LLM env vars are set.

    Per ``rules/env-models.md``, the model name comes from
    ``DEFAULT_LLM_MODEL`` (or ``OPENAI_PROD_MODEL``) and the matching
    API key MUST be present for the model's provider prefix. The
    Tier-2 gate is "real LLM endpoint reachable" — when env is unset,
    the tests SKIP (per ``rules/test-skip-discipline.md`` — acceptable
    skip with explicit reason citing the missing env var).
    """
    model = os.environ.get("DEFAULT_LLM_MODEL") or os.environ.get("OPENAI_PROD_MODEL")
    if not model:
        return False
    lower = model.lower()
    if lower.startswith(("gpt", "o1", "o3", "o4")):
        return bool(os.environ.get("OPENAI_API_KEY"))
    if lower.startswith("claude"):
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if lower.startswith("gemini"):
        return bool(
            os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        )
    # Other providers: optimistic — assume key is present if model is set.
    return True


_LLM_AVAILABLE_REASON = (
    "Tier-2 LLM probe requires DEFAULT_LLM_MODEL (or OPENAI_PROD_MODEL) plus "
    "the matching API key per rules/env-models.md model-key pairing table."
)


# --------------------------------------------------------------------------- #
# Test 1 — simple linear plan: brief → WorkflowBuilder → buildable Workflow   #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _has_llm_env(), reason=_LLM_AVAILABLE_REASON)
def test_from_brief_linear_plan_builds_executable_workflow():
    """AC 1: ``Workflow.from_brief(brief)`` returns a buildable WorkflowBuilder.

    Asserts the foundational contract the issue brief asserts in AC 1:
    the returned object is a :class:`WorkflowBuilder` whose ``.build()``
    produces a valid :class:`Workflow` without raising. Plan size is
    bounded by the fixture's expected_min/max_nodes to catch
    degenerate cases (empty plan, runaway plan).
    """
    from kailash.workflow import Workflow
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.workflow.graph import Workflow as WorkflowCls

    fixture = _load_fixture("workflow_linear.yaml")
    builder = Workflow.from_brief(fixture["brief"])

    # Probe 1 — return-type contract (structural, deterministic).
    assert isinstance(builder, WorkflowBuilder), (
        f"Workflow.from_brief MUST return WorkflowBuilder, got "
        f"{type(builder).__name__}"
    )

    # Probe 2 — buildable contract: .build() returns a Workflow.
    workflow = builder.build()
    assert isinstance(
        workflow, WorkflowCls
    ), f".build() MUST return Workflow, got {type(workflow).__name__}"

    # Probe 3 — plan size bounded by fixture expectations.
    node_count = len(workflow.nodes)
    assert node_count >= fixture["expected_min_nodes"], (
        f"plan has {node_count} nodes; expected >= " f"{fixture['expected_min_nodes']}"
    )
    assert node_count <= fixture["expected_max_nodes"], (
        f"plan has {node_count} nodes; expected <= " f"{fixture['expected_max_nodes']}"
    )


# --------------------------------------------------------------------------- #
# Test 2 — branching plan: multi-node + connection realization                #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _has_llm_env(), reason=_LLM_AVAILABLE_REASON)
def test_from_brief_branching_plan_wires_connections():
    """AC 6: connection realization works for multi-node briefs.

    Exercises the S1 realizer's :func:`realize_connections` path
    (kailash._from_brief.branching) on a brief that explicitly asks
    for two connected nodes. The probe asserts SHAPE (≥2 nodes, ≥1
    connection), not exact node names — the LLM is non-deterministic
    at byte level per ``rules/probe-driven-verification.md`` Rule 3.
    """
    from kailash.workflow import Workflow
    from kailash.workflow.builder import WorkflowBuilder

    fixture = _load_fixture("workflow_branching.yaml")
    builder = Workflow.from_brief(fixture["brief"])

    assert isinstance(builder, WorkflowBuilder)
    workflow = builder.build()

    # Probe — plan has multiple nodes (the brief asked for two).
    node_count = len(workflow.nodes)
    assert node_count >= fixture["expected_min_nodes"], (
        f"branching plan has {node_count} nodes; expected >= "
        f"{fixture['expected_min_nodes']}"
    )

    # Probe — at least one connection exists wiring the nodes together.
    # `connections` is a list on the Workflow instance per
    # src/kailash/workflow/graph.py:152.
    conn_count = len(workflow.connections)
    assert conn_count >= 1, (
        f"branching plan must have ≥1 connection wiring its nodes; "
        f"got {conn_count}. Nodes: {list(workflow.nodes.keys())}"
    )


# --------------------------------------------------------------------------- #
# Test 3 — error path: hallucinated node type → typed exception                #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _has_llm_env(), reason=_LLM_AVAILABLE_REASON)
def test_from_brief_error_path_raises_typed_exception():
    """AC 6: invalid briefs raise BriefInterpretationError with discriminator.

    The fixture brief asks for fabricated node types
    (``HyperQuantumFluxCapacitorNode``, ``TimeMachineReverseNode``).
    Two valid dispositions:

    1. The LLM emits low confidence (correctly recognizing the brief
       is implausible) → :class:`BriefInterpretationError` with
       ``low_confidence=True``.
    2. The LLM emits the made-up node type → S1's allowlist gate
       (:func:`validate_node_type`) raises
       :class:`BriefInterpretationError` with ``unknown_value=<name>``.

    Either disposition is correct; the test asserts the typed
    discriminator is set so callers can branch on the failure mode.
    """
    from kailash._from_brief.exceptions import BriefInterpretationError
    from kailash.workflow import Workflow

    fixture = _load_fixture("workflow_error_path.yaml")

    with pytest.raises(BriefInterpretationError) as exc_info:
        Workflow.from_brief(fixture["brief"])

    exc = exc_info.value
    # Probe — typed discriminator MUST be set per S1's exception contract
    # (kailash._from_brief.exceptions.BriefInterpretationError). One of the
    # three discriminators (low_confidence, unknown_value, malformed) MUST
    # carry the failure mode.
    discriminator_set = (
        exc.low_confidence or exc.unknown_value is not None or exc.malformed
    )
    assert discriminator_set, (
        f"BriefInterpretationError MUST carry a typed discriminator: "
        f"low_confidence={exc.low_confidence!r}, "
        f"unknown_value={exc.unknown_value!r}, "
        f"malformed={exc.malformed!r}. Message: {exc!s}"
    )
