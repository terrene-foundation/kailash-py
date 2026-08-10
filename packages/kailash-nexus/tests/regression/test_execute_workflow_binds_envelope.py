# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: ``Nexus._execute_workflow`` MUST bind the parameters envelope.

``_execute_workflow(self, workflow_name, inputs)`` offers the caller a SINGLE
arguments slot. Under the structural rule in
``kailash/workflow/input_envelope.py`` that means it binds: the opt-out exists
only for an entry point offering BOTH an ``inputs`` and a ``parameters`` slot,
where picking one carries meaning. There is nothing here for a caller to pick.

It was passing the caller's mapping through raw, and the defence for that was
"it is not route-registered". True, and it protects nothing, because the SDK's
own documentation makes the CALLER's route the entry point --
``skills/03-nexus/nexus-api-patterns.md:32`` teaches exactly this::

    @app.endpoint("/api/conversations/{conversation_id}", methods=["GET"])
    async def get_conversation(conversation_id: str):
        return await app._execute_workflow("chat_workflow", {"id": conversation_id})

and ``tests/integration/test_security_features.py:57`` drives the same shape
from a request body. So a workflow reading ``parameters.get("id")`` -- the
documented Nexus convention, which every other channel binds for -- raised
``NameError`` inside the SDK's own worked example, surfacing to the caller as
an opaque HTTP 500.

The tests below drive the documented example itself rather than asserting the
binder is called: whether a custom endpoint following the docs works is the
user-visible property, and it is the one that was broken.

Binding happens AFTER ``validate_workflow_inputs``, deliberately. That
validator enforces the size cap and the dangerous-key/dunder rules against
TOP-LEVEL keys only, so it must see the caller's actual mapping -- enveloping
first would both halve the effective size limit (the payload appears twice)
and move the caller's keys out of the only level the validator inspects.
"""

import pytest

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


def _nexus(port: int) -> Nexus:
    return Nexus(
        api_port=port,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )


def _workflow(code: str):
    """A one-node workflow whose PythonCodeNode runs ``code``.

    The node is NOT named after any input key: the runtime scopes a
    workflow-level input whose key matches a NODE ID into that node alone, so
    a node called ``id`` or ``parameters`` would test the scoping rule instead
    of the binding.
    """
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "reader", {"code": code})
    return builder.build()


def _result_of(results: dict) -> dict:
    """Unwrap ``{'<node>': {'result': {...}}}`` from a runtime result map."""
    assert isinstance(results, dict) and results, f"empty result map: {results!r}"
    inner = next(iter(results.values()))
    assert isinstance(inner, dict) and "result" in inner, f"unexpected: {results!r}"
    return inner["result"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_execute_workflow_binds_parameters_for_the_documented_shape():
    """``parameters.get("id")`` MUST resolve for the documented call shape.

    Falsifying result: before the bind, the node raised ``NameError: name
    'parameters' is not defined`` and ``_execute_workflow`` converted it to
    ``HTTPException(500, "Workflow execution failed")``.
    """
    app = _nexus(8291)
    app.register("chat_workflow", _workflow("result = {'echo': parameters.get('id')}"))

    try:
        results = await app._execute_workflow("chat_workflow", {"id": "conv-42"})
        assert _result_of(results) == {"echo": "conv-42"}, results
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_execute_workflow_still_binds_bare_top_level_names():
    """Existing callers reading BARE names MUST keep working.

    The envelope is bound ALONGSIDE the workflow-level splat, not instead of
    it, so this is the half that must not regress: every caller that already
    read a bare top-level name predates the envelope and would break loudly.
    """
    app = _nexus(8292)
    app.register("bare_workflow", _workflow("result = {'echo': conversation_id}"))

    try:
        results = await app._execute_workflow(
            "bare_workflow", {"conversation_id": "conv-7"}
        )
        assert _result_of(results) == {"echo": "conv-7"}, results
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_documented_custom_endpoint_example_serves_a_parameters_workflow():
    """The SDK's own worked example MUST work end-to-end over HTTP.

    This is `skills/03-nexus/nexus-api-patterns.md:32` verbatim in shape --
    a custom endpoint whose body is a single ``_execute_workflow`` call -- so
    it fails exactly when a user following the documentation would fail.

    Falsifying result: before the bind this returned HTTP 500 with
    ``{"detail": "Workflow execution failed"}``.
    """
    from fastapi.testclient import TestClient

    app = _nexus(8293)
    app.register("chat_workflow", _workflow("result = {'echo': parameters.get('id')}"))

    @app.endpoint("/api/conversations/{conversation_id}", methods=["GET"])
    async def get_conversation(conversation_id: str):
        return await app._execute_workflow("chat_workflow", {"id": conversation_id})

    try:
        fastapi_app = app.fastapi_app
        assert fastapi_app is not None, "enterprise gateway was not initialised"
        response = TestClient(fastapi_app).get("/api/conversations/conv-99")

        assert response.status_code == 200, (
            "the documented custom-endpoint example failed for a workflow "
            f"reading parameters.get(...): {response.status_code} {response.text}"
        )
        assert _result_of(response.json()) == {"echo": "conv-99"}, response.text
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_execute_workflow_envelope_wins_a_colliding_caller_key():
    """A caller key named ``parameters`` MUST lose to the envelope, as elsewhere.

    Fixed precedence shared with every other channel -- the envelope binding is
    a contract workflows depend on, so it cannot become conditional on caller
    data. The caller's own value stays reachable at ``parameters["parameters"]``.
    """
    app = _nexus(8294)
    app.register(
        "collide_workflow",
        _workflow(
            "result = {'inner': parameters.get('parameters'), 'x': parameters.get('x')}"
        ),
    )

    try:
        results = await app._execute_workflow(
            "collide_workflow", {"parameters": {"caller": "value"}, "x": 1}
        )
        assert _result_of(results) == {"inner": {"caller": "value"}, "x": 1}, results
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_size_cap_is_measured_against_the_callers_payload_not_the_envelope():
    """The size cap MUST be measured against the CALLER's payload.

    Guards the wrong bind order: enveloping BEFORE validation would measure
    the payload twice, silently halving every deployment's effective input
    limit. A payload under the cap but over half of it must still be served.
    """
    app = _nexus(8295)
    app.register(
        "size_workflow", _workflow("result = {'n': len(parameters.get('blob', ''))}")
    )
    app._max_input_size = 4096

    try:
        blob = "x" * 3000  # under 4096 raw; over it once the envelope doubles
        results = await app._execute_workflow("size_workflow", {"blob": blob})
        assert _result_of(results) == {"n": 3000}, results
    finally:
        if app._running:
            app.stop()
