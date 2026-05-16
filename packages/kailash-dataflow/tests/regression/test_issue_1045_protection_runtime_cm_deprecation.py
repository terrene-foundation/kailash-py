# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: ProtectedDataFlowRuntime must not emit the LocalRuntime
"without context manager" DeprecationWarning (issue #1045).

``ProtectedDataFlowRuntime(LocalRuntime)`` is a long-lived, framework-held
runtime. DataFlow constructs it via ``create_protected_runtime()`` and drives
``execute()`` directly — it is never used through the
``with LocalRuntime() as rt:`` context manager.

``LocalRuntime.execute()`` (src/kailash/runtime/local.py) emits

    DeprecationWarning: LocalRuntime.execute() without context manager or
    explicit close() is deprecated. ... This will become an error in v0.12.0.

on every call unless the runtime is context-managed, atexit-registered, OR
externally managed. Before the fix, ``ProtectedDataFlowRuntime.__init__``
called ``super().__init__(**kwargs)`` without declaring external management,
so the protection-enforcement hot path emitted this DeprecationWarning on
every protected workflow run — and would hard-fail in v0.12.0.

The fix calls ``self.mark_externally_managed()`` in ``__init__`` — the
SDK-blessed opt-out for framework-owned runtimes (see
``kailash.runtime.local.LocalRuntime.mark_externally_managed``, issue #478)
and the established DataFlow convention.

This test exercises the real protection ``execute()`` path against a real
(SQLite) DataFlow instance and asserts NO ``DeprecationWarning`` mentioning
the context-manager contract is emitted. The runtime-tuple contract and the
ProtectionViolation behavior are verified by the existing protection suites;
this test guards only the deprecation surface.

See issue #1045, rules/zero-tolerance.md Rule 1 (warnings are errors).
"""

from __future__ import annotations

import warnings

import pytest

_wf = pytest.importorskip("kailash.workflow.builder")
WorkflowBuilder = _wf.WorkflowBuilder

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection_middleware import ProtectedDataFlowRuntime


def _cm_deprecation_warnings(records):
    """Return DeprecationWarnings whose message is the LocalRuntime
    'without context manager' contract warning (the issue #1045 surface).

    Structural substring match against the SDK's own fixed warning string
    (kailash.runtime.local.LocalRuntime.execute) — NOT a semantic probe of
    model output. This is the exact text the SDK emits; matching it is the
    structural assertion that the deprecation gate did/didn't fire.
    """
    out = []
    for r in records:
        if issubclass(r.category, DeprecationWarning) and (
            "without context manager" in str(r.message)
        ):
            out.append(r)
    return out


@pytest.mark.regression
class TestIssue1045ProtectionRuntimeCMDeprecation:
    """ProtectedDataFlowRuntime opts out of the CM deprecation."""

    def test_protected_runtime_is_marked_externally_managed(self):
        """Structural invariant: the runtime declares external management.

        If a future refactor drops ``mark_externally_managed()`` from
        ``__init__``, ``_externally_managed`` flips back to False and the
        DeprecationWarning re-fires on every protected execute(). This
        invariant fails loudly at that point.
        """
        db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )
        try:
            runtime = db.create_protected_runtime()
            assert isinstance(runtime, ProtectedDataFlowRuntime)
            assert getattr(runtime, "_externally_managed", False) is True, (
                "ProtectedDataFlowRuntime must be externally managed so "
                "LocalRuntime.execute() does not emit the CM DeprecationWarning "
                "(issue #1045). mark_externally_managed() was likely dropped "
                "from __init__."
            )
        finally:
            db.close()

    def test_protected_execute_emits_no_cm_deprecation_warning(self):
        """Behavioral: running a workflow through the protection runtime
        emits no 'without context manager' DeprecationWarning.

        Protection is left at the permissive default (NOT read-only) so the
        execute() path is exercised without a ProtectionViolation short-
        circuiting it. The deprecation gate in LocalRuntime.execute() runs
        before workflow execution, so even if the :memory: workflow errors
        (e.g. table not yet created), the warning surface is still exercised.
        """
        db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )
        try:

            @db.model
            class Issue1045Model:
                id: int
                name: str
                value: int

            runtime = db.create_protected_runtime()
            assert isinstance(runtime, ProtectedDataFlowRuntime)

            workflow = WorkflowBuilder()
            workflow.add_node(
                "Issue1045ModelCreateNode",
                "create_it",
                {"name": "regression", "value": 1045},
            )

            with warnings.catch_warnings(record=True) as records:
                warnings.simplefilter("always")
                try:
                    runtime.execute(workflow.build())
                except Exception:
                    # Execution outcome (success / table-missing / protection)
                    # is irrelevant to this regression. The deprecation gate
                    # runs at the top of execute(), before any of that.
                    pass

            offenders = _cm_deprecation_warnings(records)
            assert not offenders, (
                "ProtectedDataFlowRuntime.execute() emitted the LocalRuntime "
                "context-manager DeprecationWarning (issue #1045 regression). "
                f"Offending message: {str(offenders[0].message)!r}"
            )
        finally:
            db.close()
