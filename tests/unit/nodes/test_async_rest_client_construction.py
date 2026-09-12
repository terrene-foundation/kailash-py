"""Construction contract for AsyncRESTClientNode (issue #2230, sub-task 3).

Root defect: ``AsyncRESTClientNode.__init__`` called ``super().__init__(**kwargs)``
— which runs config validation, which calls ``get_parameters()`` — before
assigning ``self.rest_node``, the attribute ``get_parameters()`` dereferenced.
Every construction therefore raised::

    NodeConfigurationError: Failed to get node parameters:
    'AsyncRESTClientNode' object has no attribute 'rest_node'

The node is ``@register_node()``-registered and publicly documented, so
``workflow.add_node("AsyncRESTClientNode", ...)`` failed for every user.

These tests pin the ROOT-CAUSE property, not the ordering accident: the schema
methods must not depend on instance state that ``__init__`` establishes, so a
future subclass reordering ``__init__`` cannot silently reintroduce the bug.

The synchronous ``RESTClientNode`` is asserted as an explicit CONTROL so the
suite can return the other answer: if the import or the harness were broken the
control would fail too, and a control failure means "instrument broken", not
"async node broken".
"""

from pathlib import Path

from kailash.nodes.api import rest as rest_module
from kailash.nodes.api.rest import AsyncRESTClientNode, RESTClientNode
from kailash.workflow.builder import WorkflowBuilder

_WORKTREE_ROOT = Path(__file__).resolve().parents[3]


def test_module_under_test_is_this_checkout():
    """Guard: pytest in a worktree can silently import a different checkout.

    Without this, a green run would not discriminate between "the fix in THIS
    tree works" and "another tree's already-fixed copy was imported".
    """
    assert Path(rest_module.__file__).resolve().is_relative_to(_WORKTREE_ROOT), (
        f"rest.py imported from {rest_module.__file__}, "
        f"which is outside the checkout under test ({_WORKTREE_ROOT})"
    )


# --------------------------------------------------------------------------
# CONTROL — the synchronous sibling was never broken.
# --------------------------------------------------------------------------


def test_control_sync_rest_client_constructs():
    node = RESTClientNode()
    assert node.get_parameters()
    assert node.get_output_schema()


# --------------------------------------------------------------------------
# The defect: construction, across every kwarg shape reported in #2230.
# --------------------------------------------------------------------------


def test_async_rest_client_constructs_with_no_kwargs():
    node = AsyncRESTClientNode()
    assert isinstance(node, AsyncRESTClientNode)


def test_async_rest_client_constructs_with_url_kwarg():
    node = AsyncRESTClientNode(url="")
    assert isinstance(node, AsyncRESTClientNode)


def test_async_rest_client_constructs_with_rest_kwargs():
    node = AsyncRESTClientNode(base_url="https://api.example.com/v1", resource="users")
    assert node.config["base_url"] == "https://api.example.com/v1"
    assert node.config["resource"] == "users"


# --------------------------------------------------------------------------
# Schema parity with the synchronous node — the documented contract
# ("Same parameters as the synchronous version").
# --------------------------------------------------------------------------


def test_parameters_match_sync_sibling():
    assert AsyncRESTClientNode().get_parameters() == RESTClientNode().get_parameters()


def test_output_schema_matches_sync_sibling():
    assert (
        AsyncRESTClientNode().get_output_schema()
        == RESTClientNode().get_output_schema()
    )


# --------------------------------------------------------------------------
# ROOT-CAUSE PIN: the schema methods must not read instance state at all, so
# no future __init__ reordering can reintroduce the defect.
# --------------------------------------------------------------------------


def test_schema_methods_do_not_depend_on_instance_delegates():
    """Removing the delegates must not affect get_parameters/get_output_schema.

    This is the regression-proof form of the fix: merely assigning the
    delegates earlier in __init__ would leave this test RED.
    """
    node = AsyncRESTClientNode()
    expected_params = node.get_parameters()
    expected_schema = node.get_output_schema()

    del node.rest_node
    del node.http_node

    assert node.get_parameters() == expected_params
    assert node.get_output_schema() == expected_schema


def test_schema_methods_work_on_an_uninitialized_instance():
    """A subclass that reorders __init__ still gets a working schema.

    ``__new__`` yields an instance on which ``__init__`` has never run, i.e.
    the exact state the base class validation saw when the bug fired.
    """
    bare = AsyncRESTClientNode.__new__(AsyncRESTClientNode)
    assert bare.get_parameters() == RESTClientNode().get_parameters()
    assert bare.get_output_schema() == RESTClientNode().get_output_schema()


def test_subclass_that_reorders_init_still_constructs():
    class ReorderedAsyncRESTClientNode(AsyncRESTClientNode):
        def __init__(self, **kwargs):
            self._marker = "set before super"
            super().__init__(**kwargs)

    node = ReorderedAsyncRESTClientNode(base_url="https://api.example.com")
    assert node.get_parameters() == RESTClientNode().get_parameters()


# --------------------------------------------------------------------------
# The delegates are still wired — the fix must not turn run()/async_run()
# forwarding into dead code.
# --------------------------------------------------------------------------


def test_delegates_are_still_constructed():
    node = AsyncRESTClientNode(base_url="https://api.example.com/v1")
    assert isinstance(node.rest_node, RESTClientNode)
    assert node.http_node is not None


# --------------------------------------------------------------------------
# End-to-end at the registry level: the failure users actually hit.
# --------------------------------------------------------------------------


def test_workflow_builder_can_add_and_build_async_rest_client():
    builder = WorkflowBuilder()
    builder.add_node(
        "AsyncRESTClientNode",
        "rest",
        {
            "base_url": "https://api.example.com/v1",
            "resource": "users",
            "method": "GET",
        },
    )
    workflow = builder.build()
    assert "rest" in workflow.nodes


def test_workflow_builder_control_sync_rest_client():
    builder = WorkflowBuilder()
    builder.add_node(
        "RESTClientNode",
        "rest",
        {"base_url": "https://api.example.com/v1", "resource": "users"},
    )
    assert "rest" in builder.build().nodes


# --------------------------------------------------------------------------
# Config-filtering parity. ``version`` is a declared REST parameter; the base
# class only preserves it when get_parameters() succeeds during __init__.
# --------------------------------------------------------------------------


def test_declared_version_parameter_survives_config_filtering():
    assert RESTClientNode(version="v2").config["version"] == "v2"  # CONTROL
    assert AsyncRESTClientNode(version="v2").config["version"] == "v2"
