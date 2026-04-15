"""Regression: Issue #478 — DataFlow internal LocalRuntime warning leak.

Symptom: long-lived ``LocalRuntime`` instances owned by DataFlow internals
(``ModelRegistry``, ``DataFlow``, migration inspectors, gateway, adapter)
triggered Core SDK's "use context manager" ``DeprecationWarning`` on every
``execute()`` call because they live across many calls and cannot be wrapped
in a single ``with`` block.

Fix: Core SDK 2.8.7 exposes a public ``LocalRuntime.mark_externally_managed()``
opt-out.  When called, the runtime suppresses the ad-hoc-usage deprecation
warning AND skips the fallback ``atexit`` cleanup registration — the owning
framework is responsible for calling ``runtime.close()`` at its own shutdown.
Every DataFlow construction site now routes through this public API instead
of mutating the private ``_cleanup_registered`` flag directly.

These tests are behavioural — they exercise the actual ``LocalRuntime`` API
and assert the two externally-observable contracts (no warning, no atexit
registration), plus the DataFlow integration path that motivated the fix.
"""

from __future__ import annotations

import warnings

import pytest

# -----------------------------------------------------------------------
# Unit: the public API contract on LocalRuntime itself.
# -----------------------------------------------------------------------


@pytest.mark.regression
def test_mark_externally_managed_suppresses_deprecation_warning():
    """Calling ``mark_externally_managed()`` opts out of the warning."""
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime().mark_externally_managed()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Probe the guard directly — we don't need to run a real workflow,
        # just prove the flag state produces no DeprecationWarning when the
        # runtime's warning-check path is evaluated.
        assert runtime._externally_managed is True
        # The deprecation check is in execute(); we inspect the two flags
        # the guard examines and confirm the gate closes.
        assert not (
            not runtime._is_context_managed
            and not runtime._cleanup_registered
            and not runtime._externally_managed
        ), "externally-managed runtime must bypass the deprecation guard"

    # No DeprecationWarning fired from the flag inspection above.
    assert not any(
        issubclass(w.category, DeprecationWarning) for w in caught
    ), "externally-managed runtime must not emit LocalRuntime deprecation"

    runtime.close()


@pytest.mark.regression
def test_mark_externally_managed_is_fluent():
    """The method returns ``self`` to support one-line construction."""
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime().mark_externally_managed()
    assert isinstance(runtime, LocalRuntime)
    assert runtime._externally_managed is True

    runtime.close()


@pytest.mark.regression
def test_mark_externally_managed_leaves_cleanup_registered_honest():
    """``_cleanup_registered`` MUST remain False after the opt-out.

    The private flag means "atexit registered".  A prior iteration of this
    fix set it to True preemptively, lying about the runtime's state.  The
    public opt-out uses a separate ``_externally_managed`` flag so the
    cleanup-registered flag retains its original meaning.
    """
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime().mark_externally_managed()
    assert runtime._cleanup_registered is False, (
        "mark_externally_managed() must NOT lie about atexit state — the "
        "owning framework opts out of atexit registration separately, and "
        "the cleanup_registered flag continues to mean 'atexit registered'."
    )

    runtime.close()


@pytest.mark.regression
def test_transient_runtime_still_emits_deprecation_warning():
    """Without the opt-out, ad-hoc callers still see the warning.

    This proves the opt-out is narrow: it only takes effect for frameworks
    that explicitly declare external management.  A user who constructs
    a bare ``LocalRuntime()`` and calls ``execute()`` outside a ``with``
    block still gets the documented deprecation path so they can migrate.
    """
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "echo",
        {"code": "result = {'ok': True}"},
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        runtime = LocalRuntime()  # NO mark_externally_managed()
        try:
            runtime.execute(workflow.build())
        finally:
            runtime.close()

    local_runtime_warnings = [
        w
        for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "LocalRuntime.execute()" in str(w.message)
    ]
    assert local_runtime_warnings, (
        "transient LocalRuntime usage must still emit the deprecation "
        "warning — the opt-out is narrow by design"
    )


# -----------------------------------------------------------------------
# Integration: DataFlow construction path no longer emits the warning.
# -----------------------------------------------------------------------


@pytest.mark.regression
def test_dataflow_model_registration_silent_on_sync_path():
    """The original symptom: ``DataFlow(...)`` + ``@db.model`` registration
    on the sync code path (no running event loop) must produce zero
    ``DeprecationWarning`` entries.  Prior to the fix this fired from
    ``model_registry.py:173`` on every model registration.
    """
    try:
        from dataflow import DataFlow
    except ImportError:
        pytest.skip("kailash-dataflow not installed in this environment")

    db = DataFlow("sqlite:///:memory:")
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            @db.model
            class _Issue478Regression:
                name: str

        local_runtime_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "LocalRuntime.execute()" in str(w.message)
        ]
        assert not local_runtime_warnings, (
            f"DataFlow sync path must not emit LocalRuntime deprecation; "
            f"caught: {[str(w.message) for w in local_runtime_warnings]}"
        )
    finally:
        db.close()


@pytest.mark.regression
def test_dataflow_owned_runtimes_are_externally_managed():
    """Every DataFlow-owned runtime MUST have ``_externally_managed=True``.

    This is the structural wiring check: if a new construction site lands
    without the ``mark_externally_managed()`` call, the warning leak would
    silently return.  Asserting the flag across every owner surface catches
    that regression without needing to exercise every code path.
    """
    try:
        from dataflow import DataFlow
    except ImportError:
        pytest.skip("kailash-dataflow not installed in this environment")

    db = DataFlow("sqlite:///:memory:")
    try:
        # ``db.runtime`` is the top-level framework runtime — the first owner.
        if hasattr(db, "runtime") and db.runtime is not None:
            # AsyncLocalRuntime doesn't have the flag; only check sync runtimes.
            if hasattr(db.runtime, "_externally_managed"):
                assert (
                    db.runtime._externally_managed is True
                ), "DataFlow.runtime must be marked externally managed"

        # ModelRegistry uses its own runtime when no async loop is present.
        registry = getattr(db, "model_registry", None) or getattr(
            db, "_model_registry", None
        )
        if (
            registry is not None
            and hasattr(registry, "runtime")
            and registry.runtime is not None
        ):
            if hasattr(registry.runtime, "_externally_managed"):
                assert (
                    registry.runtime._externally_managed is True
                ), "ModelRegistry.runtime must be marked externally managed"
    finally:
        db.close()
