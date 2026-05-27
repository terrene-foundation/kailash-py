# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the deterministic realizer in ``from_brief``.

These tests exercise the structural plumbing of
:mod:`kailash.workflow.from_brief` WITHOUT invoking the LLM:

- :func:`_workflow_plan_cls` — lazy Pydantic model construction.
- :func:`_signature_cls` — lazy Kaizen Signature construction.
- :func:`_coerce_node_spec` / :func:`_coerce_connection_spec` —
  per-entry shape validation with typed exception contract.
- :func:`_realize` — plan-to-WorkflowBuilder realization, including
  duplicate-id detection and connection wiring.

The LLM-mediated end-to-end path lives in
:mod:`tests.integration.kailash.test_workflow_from_brief` (Tier-2).

Per ``rules/testing.md`` § 3-Tier: Tier-1 covers the deterministic
realizer surface; Tier-2 covers the LLM-mediated pipeline; the two
tiers do NOT overlap (no LLM stubs in Tier-1).

Origin: issue #1125 AC 6 — every NEW module should have direct
test coverage; this file is the structural coverage gate for the
S2 realizer helpers (per ``rules/testing.md`` Audit Mode rule 2).
"""

from __future__ import annotations

import pytest

from kailash._from_brief.exceptions import BriefInterpretationError

# --------------------------------------------------------------------------- #
# Lazy class resolution                                                       #
# --------------------------------------------------------------------------- #


def test_workflow_plan_cls_builds_pydantic_subclass():
    """`_workflow_plan_cls()` returns a Pydantic model with required fields."""
    from kailash._from_brief.validator import BriefPlan
    from kailash.workflow.from_brief import _workflow_plan_cls

    cls = _workflow_plan_cls()

    assert issubclass(cls, BriefPlan)
    # Fields surfaced via Pydantic's `model_fields`.
    assert "nodes" in cls.model_fields
    assert "connections" in cls.model_fields
    assert "interpretation_confidence" in cls.model_fields


def test_workflow_plan_cls_caches_result():
    """`_workflow_plan_cls()` returns the same class on repeated calls."""
    from kailash.workflow.from_brief import _workflow_plan_cls

    assert _workflow_plan_cls() is _workflow_plan_cls()


def test_signature_cls_builds_kaizen_signature():
    """`_signature_cls()` returns a Kaizen Signature subclass with fields."""
    # Class B (kaizen-dependent): `_signature_cls()` builds a real Kaizen
    # Signature, which `from kaizen.signatures import ...` requires. kaizen
    # is a downstream optional package absent in the core "Test"/"Base" CI
    # jobs. Per `rules/test-skip-discipline.md` this is an ACCEPTABLE skip
    # (cannot execute without the optional dep), NOT a masked failure — the
    # skip reason names kaizen.
    pytest.importorskip("kaizen")
    from kailash._from_brief.signatures import BriefPlanSignature
    from kailash.workflow.from_brief import _signature_cls

    cls = _signature_cls()

    assert issubclass(cls, BriefPlanSignature)
    # Signature instances should be constructible without error.
    instance = cls()
    assert instance is not None


def test_signature_cls_caches_result():
    """`_signature_cls()` returns the same class on repeated calls."""
    # Class B (kaizen-dependent): `_signature_cls()` builds a real Kaizen
    # Signature. Skip without kaizen per `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    from kailash.workflow.from_brief import _signature_cls

    assert _signature_cls() is _signature_cls()


def test_workflow_module_getattr_resolves_lazy_classes():
    """`kailash.workflow.WorkflowPlan` / `WorkflowPlanSignature` resolve."""
    # Class B (kaizen-dependent): resolving `WorkflowPlanSignature` calls
    # `_signature_cls()`, which builds a real Kaizen Signature (`WorkflowPlan`
    # alone is kaizen-free, but this test asserts the Signature resolution
    # too). Skip without kaizen per `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    from kailash.workflow import WorkflowPlan, WorkflowPlanSignature
    from kailash.workflow.from_brief import _signature_cls, _workflow_plan_cls

    assert WorkflowPlan is _workflow_plan_cls()
    assert WorkflowPlanSignature is _signature_cls()


def test_workflow_module_getattr_raises_for_unknown_attr():
    """`kailash.workflow.<missing>` raises AttributeError loudly."""
    import kailash.workflow

    with pytest.raises(AttributeError, match="no attribute 'NotARealSymbol'"):
        kailash.workflow.NotARealSymbol  # noqa: B018


def test_from_brief_module_getattr_raises_for_unknown_attr():
    """`from_brief.<missing>` raises AttributeError loudly."""
    import kailash.workflow.from_brief as fb

    with pytest.raises(AttributeError, match="no attribute 'NotARealSymbol'"):
        fb.NotARealSymbol  # noqa: B018


# --------------------------------------------------------------------------- #
# Node spec coercion                                                          #
# --------------------------------------------------------------------------- #


def test_coerce_node_spec_accepts_well_formed():
    """A valid node spec round-trips through `_coerce_node_spec`."""
    from kailash.workflow.from_brief import _coerce_node_spec

    spec = _coerce_node_spec(
        {"node_type": "PythonCodeNode", "node_id": "n1", "config": {"code": "x"}}
    )
    assert spec == {
        "node_type": "PythonCodeNode",
        "node_id": "n1",
        "config": {"code": "x"},
    }


def test_coerce_node_spec_defaults_empty_config():
    """A node spec missing 'config' defaults to an empty dict."""
    from kailash.workflow.from_brief import _coerce_node_spec

    spec = _coerce_node_spec({"node_type": "PythonCodeNode", "node_id": "n1"})
    assert spec["config"] == {}


def test_coerce_node_spec_rejects_non_dict():
    """A non-dict node spec raises malformed=True."""
    from kailash.workflow.from_brief import _coerce_node_spec

    with pytest.raises(BriefInterpretationError) as exc_info:
        _coerce_node_spec("not a dict")  # type: ignore[arg-type]
    assert exc_info.value.malformed


def test_coerce_node_spec_rejects_missing_node_type():
    """A node spec missing 'node_type' raises malformed=True."""
    from kailash.workflow.from_brief import _coerce_node_spec

    with pytest.raises(BriefInterpretationError) as exc_info:
        _coerce_node_spec({"node_id": "n1"})
    assert exc_info.value.malformed


def test_coerce_node_spec_rejects_missing_node_id():
    """A node spec missing 'node_id' raises malformed=True."""
    from kailash.workflow.from_brief import _coerce_node_spec

    with pytest.raises(BriefInterpretationError) as exc_info:
        _coerce_node_spec({"node_type": "PythonCodeNode"})
    assert exc_info.value.malformed


def test_coerce_node_spec_rejects_non_dict_config():
    """A node spec with non-dict 'config' raises malformed=True."""
    from kailash.workflow.from_brief import _coerce_node_spec

    with pytest.raises(BriefInterpretationError) as exc_info:
        _coerce_node_spec(
            {"node_type": "PythonCodeNode", "node_id": "n1", "config": "string"}
        )
    assert exc_info.value.malformed


# --------------------------------------------------------------------------- #
# Connection spec coercion                                                    #
# --------------------------------------------------------------------------- #


def test_coerce_connection_spec_accepts_full_form():
    """A connection spec with all fields produces a ConnectionSpec."""
    from kailash._from_brief.branching import ConnectionSpec
    from kailash.workflow.from_brief import _coerce_connection_spec

    spec = _coerce_connection_spec(
        {
            "source_node": "a",
            "target_node": "b",
            "source_output": "out",
            "target_input": "in",
        }
    )
    assert isinstance(spec, ConnectionSpec)
    assert spec.source_node == "a"
    assert spec.target_node == "b"
    assert spec.source_output == "out"
    assert spec.target_input == "in"


def test_coerce_connection_spec_defaults_port_names():
    """A connection spec without explicit ports uses 'result'/'input'."""
    from kailash.workflow.from_brief import _coerce_connection_spec

    spec = _coerce_connection_spec({"source_node": "a", "target_node": "b"})
    assert spec.source_output == "result"
    assert spec.target_input == "input"


def test_coerce_connection_spec_rejects_missing_source():
    """A connection spec missing 'source_node' raises malformed=True."""
    from kailash.workflow.from_brief import _coerce_connection_spec

    with pytest.raises(BriefInterpretationError) as exc_info:
        _coerce_connection_spec({"target_node": "b"})
    assert exc_info.value.malformed


def test_coerce_connection_spec_rejects_missing_target():
    """A connection spec missing 'target_node' raises malformed=True."""
    from kailash.workflow.from_brief import _coerce_connection_spec

    with pytest.raises(BriefInterpretationError) as exc_info:
        _coerce_connection_spec({"source_node": "a"})
    assert exc_info.value.malformed


# --------------------------------------------------------------------------- #
# Realizer                                                                    #
# --------------------------------------------------------------------------- #


def test_realize_single_node_builds_workflow():
    """A single-node plan realizes into a buildable WorkflowBuilder."""
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.workflow.from_brief import _realize, _workflow_plan_cls

    plan_cls = _workflow_plan_cls()
    plan = plan_cls(
        nodes=[
            {
                "node_type": "PythonCodeNode",
                "node_id": "n1",
                "config": {"code": "result = 42"},
            }
        ],
        connections=[],
        interpretation_confidence=0.9,
    )

    builder = _realize(plan)
    assert isinstance(builder, WorkflowBuilder)
    workflow = builder.build()
    assert "n1" in workflow.nodes


def test_realize_two_nodes_with_connection_wires_them():
    """A two-node plan with one connection produces a wired workflow."""
    from kailash.workflow.from_brief import _realize, _workflow_plan_cls

    plan_cls = _workflow_plan_cls()
    plan = plan_cls(
        nodes=[
            {
                "node_type": "PythonCodeNode",
                "node_id": "src",
                "config": {"code": "result = [1, 2, 3]"},
            },
            {
                "node_type": "PythonCodeNode",
                "node_id": "dst",
                "config": {"code": "result = sum(input)"},
            },
        ],
        connections=[
            {"source_node": "src", "target_node": "dst"},
        ],
        interpretation_confidence=0.9,
    )

    builder = _realize(plan)
    workflow = builder.build()
    assert len(workflow.nodes) == 2
    assert len(workflow.connections) == 1


def test_realize_duplicate_node_id_raises():
    """A plan with duplicate node_ids raises malformed=True."""
    from kailash.workflow.from_brief import _realize, _workflow_plan_cls

    plan_cls = _workflow_plan_cls()
    plan = plan_cls(
        nodes=[
            {"node_type": "PythonCodeNode", "node_id": "dup", "config": {}},
            {"node_type": "PythonCodeNode", "node_id": "dup", "config": {}},
        ],
        connections=[],
        interpretation_confidence=0.9,
    )

    with pytest.raises(BriefInterpretationError) as exc_info:
        _realize(plan)
    assert exc_info.value.malformed
    assert "dup" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Registered node-type allowlist                                              #
# --------------------------------------------------------------------------- #


def test_registered_node_types_returns_non_empty_set():
    """`_registered_node_types()` returns the populated NodeRegistry,
    minus the SEC-1 denylist of code-execution nodes.
    """
    from kailash.workflow.from_brief import _registered_node_types

    types = _registered_node_types()
    assert isinstance(types, set)
    assert len(types) > 0
    # A canonical Kailash data-reader node is registered at import time.
    assert "CSVReaderNode" in types


@pytest.mark.regression
def test_workflow_from_brief_rejects_dangerous_code_execution_nodes():
    """SEC-1 regression: PythonCodeNode + AsyncPythonCodeNode MUST be
    rejected by the allowlist gate even though they are registered in
    `NodeRegistry`. A brief that asks the LLM to emit a `PythonCodeNode`
    with attacker-controlled `config.code` must NOT reach `builder.add_node`.
    See workspaces/from-brief-1125/04-validate/round-02-security.md SEC-1.
    """
    from kailash.workflow.from_brief import (
        _DANGEROUS_NODE_TYPES,
        _registered_node_types,
    )

    allowed = _registered_node_types()
    assert (
        "PythonCodeNode" not in allowed
    ), "SEC-1: PythonCodeNode MUST be in the denylist"
    assert (
        "AsyncPythonCodeNode" not in allowed
    ), "SEC-1: AsyncPythonCodeNode MUST be in the denylist"
    # Denylist constant itself MUST cover both names.
    assert "PythonCodeNode" in _DANGEROUS_NODE_TYPES
    assert "AsyncPythonCodeNode" in _DANGEROUS_NODE_TYPES
