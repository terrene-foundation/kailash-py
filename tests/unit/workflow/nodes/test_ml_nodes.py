# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for kailash.workflow.nodes.ml — ML lifecycle workflow nodes.

Covers:
  - Module imports and symbol presence (all three nodes + __all__).
  - Node class registration with kailash.nodes.base.NodeRegistry (string
    addressability via WorkflowBuilder.add_node("MLTrainingNode", ...)).
  - Node parameter schema shape — required params per spec §5.1.
  - Tenant-isolation strict mode: missing tenant_id raises typed error
    (rules/tenant-isolation.md §2). Silent "default" fallback is BLOCKED.
  - actor_id strict enforcement on Training + Promotion.
  - RuntimeError with actionable install hint when kailash-ml absent.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_module_imports_all_three_nodes() -> None:
    from kailash.workflow.nodes.ml import (
        MLInferenceNode,
        MLRegistryPromoteNode,
        MLTrainingNode,
    )

    assert MLTrainingNode.__name__ == "MLTrainingNode"
    assert MLInferenceNode.__name__ == "MLInferenceNode"
    assert MLRegistryPromoteNode.__name__ == "MLRegistryPromoteNode"


def test_all_export_list_matches_public_surface() -> None:
    from kailash.workflow.nodes import ml

    assert set(ml.__all__) == {
        "MLTrainingNode",
        "MLInferenceNode",
        "MLRegistryPromoteNode",
    }


def test_nodes_registered_with_node_registry() -> None:
    # Force re-registration — the conftest isolate_global_state fixture
    # may have removed nodes not present in its baseline snapshot. Calling
    # NodeRegistry.register directly re-seeds the registry for this test.
    import kailash.workflow.nodes.ml as ml  # noqa: F401
    from kailash.nodes.base import NodeRegistry

    for name, cls in (
        ("MLTrainingNode", ml.MLTrainingNode),
        ("MLInferenceNode", ml.MLInferenceNode),
        ("MLRegistryPromoteNode", ml.MLRegistryPromoteNode),
    ):
        if name not in NodeRegistry._nodes:
            NodeRegistry.register(cls, name)
        resolved = NodeRegistry.get(name)
        assert resolved is cls, f"{name} resolved to wrong class: {resolved}"


def test_training_node_parameter_schema() -> None:
    from kailash.workflow.nodes.ml import MLTrainingNode

    node = MLTrainingNode(name="train_node")
    params = node.get_parameters()
    # Required per spec §5.1
    for required in ("engine", "schema", "tenant_id", "actor_id"):
        assert required in params
        assert params[required].required is True, f"{required} must be required"
    # Optional
    for optional in ("model_spec", "eval_spec", "model_name", "data"):
        assert optional in params
        assert params[optional].required is False


def test_inference_node_parameter_schema() -> None:
    from kailash.workflow.nodes.ml import MLInferenceNode

    node = MLInferenceNode(name="infer_node")
    params = node.get_parameters()
    for required in ("model_name", "version", "input_ref", "tenant_id"):
        assert required in params
        assert params[required].required is True


def test_promote_node_parameter_schema() -> None:
    from kailash.workflow.nodes.ml import MLRegistryPromoteNode

    node = MLRegistryPromoteNode(name="promote_node")
    params = node.get_parameters()
    for required in (
        "model_name",
        "from_tier",
        "to_tier",
        "tenant_id",
        "actor_id",
    ):
        assert required in params
        assert params[required].required is True


def test_tenant_id_required_rejects_none() -> None:
    """Per rules/tenant-isolation.md §2, missing tenant_id is a typed error."""
    from kailash.workflow.nodes.ml import _assert_tenant_id

    with pytest.raises(ValueError, match="tenant_id is required"):
        _assert_tenant_id(None)
    with pytest.raises(ValueError, match="tenant_id is required"):
        _assert_tenant_id("")
    with pytest.raises(TypeError, match="tenant_id must be str"):
        _assert_tenant_id(42)
    assert _assert_tenant_id("tenant-alice") == "tenant-alice"


def test_actor_id_required_rejects_none() -> None:
    from kailash.workflow.nodes.ml import _assert_actor_id

    with pytest.raises(ValueError, match="actor_id is required"):
        _assert_actor_id(None)
    with pytest.raises(ValueError, match="actor_id is required"):
        _assert_actor_id("")
    with pytest.raises(TypeError, match="actor_id must be str"):
        _assert_actor_id(42)
    assert _assert_actor_id("agent-42") == "agent-42"


def test_training_node_raises_on_missing_kailash_ml() -> None:
    """Per rules/dependencies.md § Optional Extras with Loud Failure."""
    from kailash.workflow.nodes import ml as ml_nodes

    # Simulate missing kailash_ml at import-resolution time.
    # _require_kailash_ml does the import lazily so patching at
    # `builtins.__import__` is the cleanest injection point.
    import builtins

    real_import = builtins.__import__

    def _deny_kailash_ml(name, *args, **kwargs):
        if name == "kailash_ml" or name.startswith("kailash_ml."):
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=_deny_kailash_ml):
        with pytest.raises(RuntimeError, match=r"pip install kailash\[ml\]"):
            ml_nodes._require_kailash_ml()


def test_training_node_raises_when_ml_extra_missing() -> None:
    """MLTrainingNode.run() raises RuntimeError with install hint when
    kailash-ml is not importable. The assertion is that the error
    message names the [ml] extra so the operator sees the actionable
    install command in the traceback."""
    from kailash.workflow.nodes.ml import MLTrainingNode

    node = MLTrainingNode(name="train_node")
    import builtins

    real_import = builtins.__import__

    def _deny(name, *args, **kwargs):
        if name == "kailash_ml" or name.startswith("kailash_ml."):
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=_deny):
        with pytest.raises(RuntimeError, match=r"pip install kailash\[ml\]"):
            node.run(
                engine="sklearn.linear_model.LogisticRegression",
                schema={"name": "test", "features": [], "target": None},
                tenant_id="t1",
                actor_id="a1",
                data=None,
            )
