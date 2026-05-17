"""Regression test for issue #1071 Gap B — @app.handler() instance-API warning.

`nexus.Nexus().handler("name")` builds its workflow internally via
`make_handler_workflow` → `WorkflowBuilder.add_node_instance(node, id)`, which
historically emitted the consumer-facing instance-API advisory
("Instance-based API usage detected ...") once per registered handler — scaling
to hundreds of spurious UserWarnings per process for CORRECT decorator use.
The consumer wrote zero instance `add_node` calls; the advisory was a false
positive.

The root-cause fix routes the decorator's internal registration through
`add_node_instance(node, id, _internal=True)`, which suppresses the advisory
ONLY for the SDK-internal path. Genuine consumer instance-API misuse never
sets `_internal` and MUST still warn.

Tier 2 — real Nexus + real WorkflowBuilder, no mocking.
"""

import warnings

import pytest

_ADVISORY = "Instance-based API usage detected"


def _instance_warnings(caught):
    return [w for w in caught if _ADVISORY in str(w.message)]


def test_app_handler_decorator_emits_no_instance_api_warning():
    """@app.handler() registration MUST NOT emit the instance-API advisory."""
    from nexus import Nexus

    app = Nexus()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            @app.handler("greet")
            async def greet(name: str) -> dict:
                return {"message": f"hi {name}"}

        assert _instance_warnings(caught) == [], (
            "@app.handler() emitted the consumer-facing instance-API advisory; "
            "the decorator-internal registration path must set _internal=True"
        )
    finally:
        app.close()


def test_register_handler_programmatic_emits_no_instance_api_warning():
    """The non-decorator register_handler() path is also internal — no advisory."""
    from nexus import Nexus

    app = Nexus()
    try:

        async def ping(payload: str = "") -> dict:
            return {"pong": payload}

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            app.register_handler("ping", ping)

        assert _instance_warnings(caught) == []
    finally:
        app.close()


def test_genuine_consumer_instance_add_node_still_warns():
    """Genuine consumer add_node(<instance>, id) MUST still emit the advisory.

    The fix must NOT blanket-suppress the advisory — only the SDK-internal
    decorator path. This guards against the over-broad-suppression failure.
    """
    from kailash.nodes.base import Node
    from kailash.workflow.builder import WorkflowBuilder

    class _ConsumerNode(Node):
        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            return {}

        async def async_run(self, **kwargs):
            return {}

    builder = WorkflowBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        builder.add_node(_ConsumerNode(), "consumer_node")

    assert len(_instance_warnings(caught)) == 1, (
        "genuine consumer add_node(<instance>) must still warn — the "
        "_internal bypass must not leak to the consumer path"
    )


def test_genuine_consumer_add_node_instance_still_warns():
    """Public add_node_instance() default (no _internal) MUST still warn."""
    from kailash.nodes.base import Node
    from kailash.workflow.builder import WorkflowBuilder

    class _ConsumerNode(Node):
        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            return {}

        async def async_run(self, **kwargs):
            return {}

    builder = WorkflowBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        builder.add_node_instance(_ConsumerNode(), "consumer_node")

    assert len(_instance_warnings(caught)) == 1


def test_internal_flag_suppresses_only_when_explicitly_set():
    """add_node_instance(..., _internal=True) suppresses; default warns."""
    from kailash.nodes.base import Node
    from kailash.workflow.builder import WorkflowBuilder

    class _N(Node):
        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            return {}

        async def async_run(self, **kwargs):
            return {}

    builder = WorkflowBuilder()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        builder.add_node_instance(_N(), "n_internal", _internal=True)

    assert _instance_warnings(caught) == []
