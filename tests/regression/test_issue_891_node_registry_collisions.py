"""Regression tests for issue #891 — node-registry name collisions.

Three pairs of distinct node classes each registered the same global
``NodeRegistry`` name, making ``add_node("<name>")`` resolve to whichever
class was imported last (import-order-dependent dispatch):

- ``HybridSearchNode`` — kailash-dataflow vector node vs kailash-kaizen RAG node
- ``BulkUpsertNode``   — kailash core node vs kailash-dataflow node
- ``AggregateNode``    — dataflow.aggregate_operations vs dataflow.mongodb_nodes

The fix renames the colliding classes to distinct names and adds a core-SDK
guard that raises ``NodeConfigurationError`` on any future cross-module name
collision (while leaving same-module re-registration — DataFlow model
decoration — non-fatal per ADR-002).

These tests import all three packages in one process (the exact scenario the
collision needed) and assert each shape is reachable via a non-colliding
identifier, the old bare names are gone, and the guard fires correctly.
"""

from __future__ import annotations

import inspect

import pytest

from kailash.nodes.base import Node, NodeRegistry
from kailash.sdk_exceptions import NodeConfigurationError


def _force_import_node_modules() -> None:
    """Import the node modules so their @register_node decorators run."""
    import dataflow.nodes.aggregate_operations  # noqa: F401
    import dataflow.nodes.bulk_upsert  # noqa: F401
    import dataflow.nodes.mongodb_nodes  # noqa: F401
    import dataflow.nodes.vector_nodes  # noqa: F401
    import kailash.nodes.data.bulk_operations  # noqa: F401
    import kaizen.nodes.ai.hybrid_search  # noqa: F401


@pytest.mark.regression
def test_issue_891_renamed_nodes_resolve_to_expected_classes():
    """Each renamed node resolves in the registry to exactly one class."""
    _force_import_node_modules()

    expected = {
        "PgVectorHybridSearchNode": "dataflow.nodes.vector_nodes",
        "SemanticHybridSearchNode": "kaizen.nodes.ai.hybrid_search",
        "SQLBulkUpsertNode": "kailash.nodes.data.bulk_operations",
        "DataFlowBulkUpsertNode": "dataflow.nodes.bulk_upsert",
        "AggregateNode": "dataflow.nodes.aggregate_operations",
        "MongoAggregateNode": "dataflow.nodes.mongodb_nodes",
    }
    for name, module_tail in expected.items():
        cls = NodeRegistry._nodes.get(name)
        assert cls is not None, f"{name} not registered"
        # tolerate the `src.`-prefixed dual-import spelling
        assert cls.__module__.endswith(
            module_tail
        ), f"{name} resolved to {cls.__module__}, expected …{module_tail}"


@pytest.mark.regression
def test_issue_891_old_colliding_names_no_longer_registered():
    """The bare colliding names HybridSearchNode / BulkUpsertNode are gone.

    AggregateNode is intentionally still registered — it is kept by
    dataflow.aggregate_operations (the convention owner); only the mongodb
    side was renamed to MongoAggregateNode.
    """
    _force_import_node_modules()
    assert "HybridSearchNode" not in NodeRegistry._nodes
    assert "BulkUpsertNode" not in NodeRegistry._nodes


@pytest.mark.regression
def test_issue_891_dataflow_hybridsearch_deprecation_alias():
    """dataflow's public HybridSearchNode symbol still imports (one cycle).

    The alias is a plain module assignment — NOT re-decorated — so it does
    not re-register the bare name and re-open the collision.
    """
    from dataflow.nodes import HybridSearchNode, PgVectorHybridSearchNode

    assert HybridSearchNode is PgVectorHybridSearchNode


def _probe_node_class(name: str) -> type[Node]:
    """Build a minimal valid Node subclass for guard probes."""

    def get_parameters(self):  # noqa: ANN001
        return {}

    def run(self, **kwargs):  # noqa: ANN001, ANN003
        return {}

    return type(name, (Node,), {"get_parameters": get_parameters, "run": run})


@pytest.mark.regression
def test_issue_891_cross_module_collision_raises():
    """Two distinct classes from different source files cannot share a name."""
    probe_a = _probe_node_class("_Issue891ProbeA")
    probe_b = _probe_node_class("_Issue891ProbeB")
    # point the probes at two real, distinct source files
    probe_a.__module__ = "json.decoder"
    probe_b.__module__ = "json.encoder"
    assert inspect.getfile(probe_a) != inspect.getfile(probe_b)

    alias = "_Issue891CollisionProbe"
    NodeRegistry.register(probe_a, alias=alias)
    try:
        with pytest.raises(NodeConfigurationError, match="collision"):
            NodeRegistry.register(probe_b, alias=alias)
    finally:
        NodeRegistry._nodes.pop(alias, None)


@pytest.mark.regression
def test_issue_891_same_module_reregistration_allowed():
    """Same-module re-registration stays non-fatal (ADR-002 / DataFlow models)."""
    probe_a = _probe_node_class("_Issue891SameModA")
    probe_b = _probe_node_class("_Issue891SameModB")
    # same source file → DataFlow model-decoration pattern (fresh class, same module)
    probe_a.__module__ = "json.decoder"
    probe_b.__module__ = "json.decoder"

    alias = "_Issue891SameModuleProbe"
    NodeRegistry.register(probe_a, alias=alias)
    try:
        # must NOT raise
        NodeRegistry.register(probe_b, alias=alias)
        assert NodeRegistry._nodes[alias] is probe_b
    finally:
        NodeRegistry._nodes.pop(alias, None)


@pytest.mark.regression
def test_issue_891_allow_override_exempts_dynamic_registration():
    """allow_override=True exempts the cross-module guard, in either order.

    DataFlow @db.model regenerates CRUD node classes whose names may coincide
    with static nodes (e.g. a `Document` model's generated `DocumentCountNode`
    vs the static `mongodb_nodes.DocumentCountNode`). The overwrite is
    intentional — the guard must not fire on it.
    """
    static_probe = _probe_node_class("_Issue891OvStatic")
    dynamic_probe = _probe_node_class("_Issue891OvDynamic")
    static_probe.__module__ = "json.decoder"
    dynamic_probe.__module__ = "json.encoder"  # different file → would collide
    alias = "_Issue891OverrideProbe"

    # Order A — dynamic registers first; a later static registration of the
    # same name from a different module must NOT raise (incumbent is dynamic).
    NodeRegistry.register(dynamic_probe, alias=alias, allow_override=True)
    try:
        NodeRegistry.register(static_probe, alias=alias)
        assert NodeRegistry._nodes[alias] is static_probe
    finally:
        NodeRegistry._nodes.pop(alias, None)
        NodeRegistry._dynamic_names.discard(alias)

    # Order B — static registers first; a later dynamic registration
    # (allow_override=True) of the same name must NOT raise.
    NodeRegistry.register(static_probe, alias=alias)
    try:
        NodeRegistry.register(dynamic_probe, alias=alias, allow_override=True)
        assert NodeRegistry._nodes[alias] is dynamic_probe
    finally:
        NodeRegistry._nodes.pop(alias, None)
        NodeRegistry._dynamic_names.discard(alias)


@pytest.mark.regression
def test_issue_891_dynamic_exemption_does_not_outlive_the_dynamic_node():
    """The allow_override exemption tracks the LIVE incumbent, not the name.

    Once a static node takes a slot previously held by a dynamic node, a
    genuine static-vs-static cross-module collision on that name MUST still
    raise — the exemption must not be permanently sticky (issue #891).
    """
    dynamic_probe = _probe_node_class("_Issue891StickyDynamic")
    static_a = _probe_node_class("_Issue891StickyStaticA")
    static_b = _probe_node_class("_Issue891StickyStaticB")
    dynamic_probe.__module__ = "json.decoder"
    static_a.__module__ = "json.encoder"
    static_b.__module__ = "json.scanner"  # third distinct real file
    alias = "_Issue891StickyProbe"

    try:
        # 1. dynamic registers — name is now exempt
        NodeRegistry.register(dynamic_probe, alias=alias, allow_override=True)
        assert alias in NodeRegistry._dynamic_names
        # 2. a static node takes the slot — exemption must be revoked
        NodeRegistry.register(static_a, alias=alias)
        assert alias not in NodeRegistry._dynamic_names
        # 3. a second static node, different module — genuine #891 collision,
        #    MUST raise even though the name was once dynamic
        with pytest.raises(NodeConfigurationError, match="collision"):
            NodeRegistry.register(static_b, alias=alias)
    finally:
        NodeRegistry._nodes.pop(alias, None)
        NodeRegistry._dynamic_names.discard(alias)
