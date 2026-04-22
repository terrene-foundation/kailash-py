# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W14 Tier-1 unit tests — tenant + actor contextvar accessors.

Per ``specs/ml-tracking.md`` §10.1 + §10.2 + §8.1, the public accessors
``get_current_run`` / ``get_current_tenant_id`` / ``get_current_actor_id``
MUST reflect the ambient ``km.track(...)`` scope without callers reaching
into internal ``ContextVar`` objects.

These tests cover the five failure modes a contextvar implementation
most often ships with:

1. Accessors leak past ``__aexit__`` — a test after the run still sees
   the prior tenant/actor. Caught by ``test_accessors_reset_after_exit``.
2. Nested runs overwrite the outer scope's values permanently — the
   outer ``__aexit__`` restores nothing. Caught by
   ``test_nested_runs_restore_outer_tenant_actor``.
3. Env-var fallback ignored — a caller sets ``KAILASH_ACTOR_ID`` but
   the run records ``None``. Caught by
   ``test_actor_id_falls_back_to_env_var``.
4. Query primitives do not read the contextvar — a
   ``tracker.list_runs()`` inside ``km.track(tenant_id="acme")`` returns
   other tenants. Caught by
   ``test_list_runs_auto_scopes_to_ambient_tenant``.
5. ``actor_id`` surfaces as a per-call kwarg on mutations (HIGH-4
   round-1 finding). Caught by
   ``test_log_metric_does_not_accept_actor_id_kwarg``.
"""
from __future__ import annotations

import inspect

import pytest
from kailash_ml.tracking import (
    ExperimentTracker,
    get_current_actor_id,
    get_current_run,
    get_current_tenant_id,
)

# ---------------------------------------------------------------------------
# Baseline — accessors return None outside any run
# ---------------------------------------------------------------------------


def test_accessors_return_none_outside_run() -> None:
    """All three accessors MUST return None when no ``km.track()`` is active."""
    assert get_current_run() is None
    assert get_current_tenant_id() is None
    assert get_current_actor_id() is None


# ---------------------------------------------------------------------------
# Set + reset semantics around the async-context boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_and_actor_bound_during_run() -> None:
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track(
            "exp", tenant_id="acme", actor_id="alice@acme.com"
        ) as run:
            assert get_current_run() is run
            assert get_current_tenant_id() == "acme"
            assert get_current_actor_id() == "alice@acme.com"
            # ExperimentRun attrs mirror the resolved values
            assert run.tenant_id == "acme"
            assert run.actor_id == "alice@acme.com"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_accessors_reset_after_exit() -> None:
    """Failure mode 1 — accessors MUST return None after ``__aexit__``."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("exp", tenant_id="acme", actor_id="alice"):
            pass
        assert get_current_run() is None
        assert get_current_tenant_id() is None
        assert get_current_actor_id() is None
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_nested_runs_restore_outer_tenant_actor() -> None:
    """Failure mode 2 — outer scope's bindings MUST be restored."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("outer", tenant_id="acme", actor_id="alice"):
            assert get_current_tenant_id() == "acme"
            assert get_current_actor_id() == "alice"
            async with tracker.track("inner", tenant_id="beta", actor_id="bob"):
                assert get_current_tenant_id() == "beta"
                assert get_current_actor_id() == "bob"
            # Inner exited — outer restored
            assert get_current_tenant_id() == "acme"
            assert get_current_actor_id() == "alice"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_nested_runs_inherit_outer_when_inner_omits() -> None:
    """Inner run without explicit tenant/actor MUST inherit outer scope."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("outer", tenant_id="acme", actor_id="alice"):
            # Inner omits both — should inherit via contextvar
            async with tracker.track("inner") as inner_run:
                assert inner_run.tenant_id == "acme"
                assert inner_run.actor_id == "alice"
                assert get_current_tenant_id() == "acme"
                assert get_current_actor_id() == "alice"
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# Env-var fallback (spec §7.2 / §8.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_actor_id_falls_back_to_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure mode 3 — ``KAILASH_ACTOR_ID`` env var MUST be honored."""
    monkeypatch.setenv("KAILASH_ACTOR_ID", "svc-account-42")
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("exp") as run:
            assert run.actor_id == "svc-account-42"
            assert get_current_actor_id() == "svc-account-42"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_actor_id_explicit_kwarg_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit ``actor_id=`` kwarg MUST override env var."""
    monkeypatch.setenv("KAILASH_ACTOR_ID", "svc-account-42")
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("exp", actor_id="alice@acme.com") as run:
            assert run.actor_id == "alice@acme.com"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_tenant_id_falls_back_to_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §7.2 — ``KAILASH_TENANT_ID`` env var fallback."""
    monkeypatch.setenv("KAILASH_TENANT_ID", "env-tenant")
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("exp") as run:
            assert run.tenant_id == "env-tenant"
            assert get_current_tenant_id() == "env-tenant"
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# Query-primitive auto-scope (spec §10.2 consumer side)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_auto_scopes_to_ambient_tenant() -> None:
    """Failure mode 4 — ``list_runs()`` with ``tenant_id=None`` inside a
    ``km.track(tenant_id="acme")`` scope MUST only return acme's runs.

    The contextvar is the defence against a classified query leaking
    another tenant's runs into a user's dashboard. Without the
    auto-scope, the default ``tenant_id=None`` falls through to an
    unscoped query and every tenant's data surfaces.
    """
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        # Seed two tenants' runs outside any ambient scope
        async with tracker.track("shared", tenant_id="acme"):
            pass
        async with tracker.track("shared", tenant_id="beta"):
            pass

        # Inside ambient tenant scope — omit tenant_id kwarg
        async with tracker.track("probe", tenant_id="acme"):
            df = await tracker.list_runs(experiment="shared")
            # Only acme's "shared" run should surface (not beta's)
            tenants = set(df["tenant_id"].to_list())
            assert tenants == {"acme"}, (
                f"contextvar auto-scope failed: list_runs inside "
                f"tenant_id=acme returned tenants={tenants}"
            )
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# HIGH-4 round-1 finding — actor MUST NOT be a per-call kwarg
# ---------------------------------------------------------------------------


def test_log_metric_does_not_accept_actor_id_kwarg() -> None:
    """Spec §8.1 — ``actor_id`` MUST NOT surface as a per-call kwarg.

    Structural invariant: if a future refactor adds ``actor_id=`` to
    any mutation primitive's signature, this test fails loudly and
    forces a re-audit against the HIGH-4 round-1 finding.
    """
    from kailash_ml.tracking.runner import ExperimentRun

    for method_name in (
        "log_param",
        "log_params",
        "log_metric",
        "log_metrics",
        "log_artifact",
        "log_figure",
        "log_model",
        "add_tag",
        "add_tags",
        "set_tags",
        "attach_training_result_async",
    ):
        method = getattr(ExperimentRun, method_name)
        sig = inspect.signature(method)
        assert "actor_id" not in sig.parameters, (
            f"{method_name}{sig} accepts actor_id kwarg — spec §8.1 "
            f"(HIGH-4 round-1 finding) requires actor to be session-level, "
            f"not per-call. Remove the kwarg or re-audit the spec decision."
        )


def test_log_metric_does_not_accept_tenant_id_kwarg() -> None:
    """Spec §7.2 HIGH-4 — ``tenant_id`` is also session-level, not per-call."""
    from kailash_ml.tracking.runner import ExperimentRun

    for method_name in (
        "log_param",
        "log_params",
        "log_metric",
        "log_metrics",
        "log_artifact",
        "log_figure",
        "log_model",
        "add_tag",
        "add_tags",
        "set_tags",
        "attach_training_result_async",
    ):
        method = getattr(ExperimentRun, method_name)
        sig = inspect.signature(method)
        assert "tenant_id" not in sig.parameters, (
            f"{method_name}{sig} accepts tenant_id kwarg — spec §7.2 "
            f"(HIGH-4 round-1 finding) blocks per-call tenant plumbing."
        )


def test_public_accessors_exported_from_tracking_package() -> None:
    """Spec §10 — all three accessors MUST be importable from
    ``kailash_ml.tracking`` AND appear in ``__all__``."""
    import kailash_ml.tracking as tracking

    for name in ("get_current_run", "get_current_tenant_id", "get_current_actor_id"):
        assert hasattr(tracking, name), f"{name} missing from tracking module"
        assert name in tracking.__all__, f"{name} missing from __all__"
        assert callable(getattr(tracking, name))


def test_internal_contextvars_are_prefixed_private() -> None:
    """Spec §10.1 — internal ContextVars MUST be underscore-prefixed
    to signal library-caller access is BLOCKED."""
    from kailash_ml.tracking import runner

    for name in ("_current_run", "_current_tenant_id", "_current_actor_id"):
        assert hasattr(runner, name), f"{name} missing from runner module"
