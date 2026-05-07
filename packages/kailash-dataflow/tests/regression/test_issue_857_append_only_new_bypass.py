"""Tier 2 regression tests for issue #857 — AppendOnlyForbiddenNode.__new__ bypass.

PR #856 (issue #839 follow-up) wired ``_check_append_only`` into 14 mutation
methods. The forbidden-mutation node stub raises ``AppendOnlyViolationError``
from ``__init__`` so ``WorkflowBuilder.add_node("<Model>UpdateNode", ...)``
fails loudly at construction time.

#856 reviewer surfaced a residual bypass class: a caller who skips ``__init__``
via ``NodeClass.__new__(NodeClass)`` would land on the concrete ``run()`` stub
which previously returned ``{}`` — the security promise of
``@db.model(append_only=True)`` would be silently violated for that one
construction path.

This module verifies the defense-in-depth fix at ``run()``: even when the
node is constructed via ``__new__`` (skipping ``__init__``), invoking
``run({})`` MUST raise the same typed ``AppendOnlyViolationError``.

Per `rules/testing.md` Tier 2: NO mocking, behavioral assertions, real
dispatch through the SDK's node-generation path.
"""

import pytest

from dataflow import DataFlow
from dataflow.exceptions import AppendOnlyViolationError


@pytest.mark.regression
def test_append_only_forbidden_node_new_bypass_run_raises_typed_error():
    """``run({})`` invoked on a ``__new__``-bypassed instance MUST raise
    ``AppendOnlyViolationError`` with the same actionable message users
    see at construction time.

    Issue #857: prior to this fix, ``run()`` returned ``{}`` and the
    documented append-only refusal silently never fired for any code
    path that constructed the node via ``Cls.__new__(Cls)`` (skipping
    ``__init__``).
    """
    db = DataFlow("sqlite:///:memory:")

    @db.model(append_only=True)
    class EventLog:
        event_type: str
        payload: str

    # Resolve the forbidden node class through the SDK's registry.
    # ``DataFlow._nodes`` is where ``NodeGenerator.generate_crud_nodes``
    # registers the per-model stubs (see core/nodes.py:447).
    update_node_cls = db._nodes.get("EventLogUpdateNode")
    assert update_node_cls is not None, (
        "EventLogUpdateNode must be registered as the forbidden stub "
        "for an append_only=True model"
    )

    # Bypass __init__ via __new__ — this is the exact attack surface
    # #857 hardens. CPython's ABC gate is satisfied because the class
    # provides concrete get_parameters / run bodies.
    bypassed_instance = update_node_cls.__new__(update_node_cls)

    # Defense in depth: run() MUST raise the same typed error that
    # __init__ raises on the construction path.
    with pytest.raises(AppendOnlyViolationError) as exc_info:
        bypassed_instance.run()

    # The error message MUST cite the model and operation so audit
    # trails and incident response can grep for it. Same message
    # contract as the __init__ path.
    msg = str(exc_info.value)
    assert "EventLog" in msg, f"error message must name the model; got: {msg!r}"
    assert (
        "append-only" in msg.lower()
    ), f"error message must explain the refusal class; got: {msg!r}"
    assert (
        "#839" in msg
    ), f"error message must reference the originating issue; got: {msg!r}"


@pytest.mark.regression
def test_append_only_forbidden_node_new_bypass_run_with_kwargs_raises():
    """``run(**kwargs)`` with arbitrary inputs on a ``__new__``-bypassed
    instance MUST also raise — the refusal contract holds regardless of
    what payload the bypass attempt supplies.
    """
    db = DataFlow("sqlite:///:memory:")

    @db.model(append_only=True)
    class AuditEntry:
        actor: str
        action: str

    delete_node_cls = db._nodes.get("AuditEntryDeleteNode")
    assert (
        delete_node_cls is not None
    ), "AuditEntryDeleteNode must be registered as the forbidden stub"

    bypassed_instance = delete_node_cls.__new__(delete_node_cls)

    with pytest.raises(AppendOnlyViolationError):
        # Arbitrary kwargs — the refusal MUST fire before any payload
        # processing.
        bypassed_instance.run(filter={"id": 1}, force=True)
