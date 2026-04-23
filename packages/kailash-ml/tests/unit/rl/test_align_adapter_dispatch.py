# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash_ml.rl.align_adapter`` + ``km.rl_train``
bridge dispatch.

Covers spec §3.1 (dispatch routing) + §7 (dependency topology):

* ``resolve_bridge_adapter`` raises ``FeatureNotAvailableError`` with
  an actionable ``[rl-bridge]`` message when kailash-align is not
  importable OR when the installed align does not register the algo.
* ``register_bridge_adapter`` is idempotent for the same class and
  raises on conflict for different classes.
* ``km.rl_train(algo="dpo", ...)`` surfaces the same
  ``FeatureNotAvailableError`` when no bridge is registered and
  kailash-align is not available — proves the dispatcher rides the
  same contract as direct resolver calls.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from kailash_ml.rl.align_adapter import (
    BRIDGE_ADAPTERS,
    FeatureNotAvailableError,
    register_bridge_adapter,
    resolve_bridge_adapter,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshot + restore ``BRIDGE_ADAPTERS`` around each test.

    The registry is module-scope state; tests that register adapters
    would otherwise leak into other tests in the same session.
    """
    snapshot = dict(BRIDGE_ADAPTERS)
    BRIDGE_ADAPTERS.clear()
    try:
        yield
    finally:
        BRIDGE_ADAPTERS.clear()
        BRIDGE_ADAPTERS.update(snapshot)


class _DummyAdapter:
    """Minimal shape that could pass Protocol if fully implemented.

    These tests don't check ``isinstance(RLLifecycleProtocol)``; they
    check the REGISTRY contract (register / resolve / error mapping).
    """

    name = "dummy"
    paradigm = "rlhf"
    buffer_kind = "preference"


def test_resolve_bridge_unknown_algo_raises_feature_not_available() -> None:
    """Spec §7: unknown algo + align not importable -> typed error
    with ``[rl-bridge]`` in the message."""
    # Mock importlib.import_module to simulate kailash-align absent.
    with patch(
        "kailash_ml.rl.align_adapter.importlib.import_module",
        side_effect=ImportError("No module named 'kailash_align.rl_bridge'"),
    ):
        with pytest.raises(FeatureNotAvailableError) as exc_info:
            resolve_bridge_adapter("dpo")

    assert exc_info.value.algo_name == "dpo"
    assert "kailash-align[rl-bridge]" in str(exc_info.value)
    assert "pip install" in str(exc_info.value)


def test_resolve_bridge_registered_algo_returns_class() -> None:
    """When the algo is pre-registered, the resolver returns immediately
    without importing kailash-align."""
    register_bridge_adapter("dummy", _DummyAdapter)
    with patch(
        "kailash_ml.rl.align_adapter.importlib.import_module",
        side_effect=AssertionError("must not import kailash-align"),
    ):
        result = resolve_bridge_adapter("dummy")

    assert result is _DummyAdapter


def test_resolve_bridge_import_succeeds_but_still_unregistered() -> None:
    """Align is installed but does not ship ``algo_name``.

    Spec §7: raise FeatureNotAvailableError with a distinct message
    pointing at a version-drift / typo diagnosis.
    """
    with patch(
        "kailash_ml.rl.align_adapter.importlib.import_module",
        return_value=object(),  # import "succeeds" but registers nothing
    ):
        with pytest.raises(FeatureNotAvailableError) as exc_info:
            resolve_bridge_adapter("nonexistent-algo")

    assert exc_info.value.algo_name == "nonexistent-algo"
    # The second error form names the available set (possibly empty).
    assert "not registered" in str(exc_info.value)


def test_register_bridge_adapter_idempotent() -> None:
    """Re-registering the exact same class under the same name is OK."""
    register_bridge_adapter("dummy", _DummyAdapter)
    # Second call with the same class must not raise.
    register_bridge_adapter("dummy", _DummyAdapter)
    assert BRIDGE_ADAPTERS["dummy"] is _DummyAdapter


def test_register_bridge_adapter_conflict_raises() -> None:
    """Re-registering a DIFFERENT class under the same name MUST raise."""

    class _OtherAdapter:
        name = "dummy"
        paradigm = "rlhf"
        buffer_kind = "preference"

    register_bridge_adapter("dummy", _DummyAdapter)
    with pytest.raises(ValueError, match="already registered"):
        register_bridge_adapter("dummy", _OtherAdapter)


def test_register_bridge_adapter_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        register_bridge_adapter("", _DummyAdapter)


def test_register_bridge_adapter_rejects_non_class() -> None:
    with pytest.raises(ValueError, match="must be a class"):
        register_bridge_adapter("x", "not a class")  # type: ignore[arg-type]


def test_feature_not_available_error_has_algo_name_attribute() -> None:
    """Consumers (tests, error handlers) MUST be able to read the
    failing algo name off the exception without parsing the message."""
    try:
        raise FeatureNotAvailableError("kto")
    except FeatureNotAvailableError as exc:
        assert exc.algo_name == "kto"
        assert "kto" in str(exc)


def test_feature_not_available_error_accepts_custom_message() -> None:
    """Custom message overrides the default template."""
    err = FeatureNotAvailableError(
        "simpo",
        message="simpo needs trl>=0.12; install kailash-align[rl-bridge]",
    )
    assert err.algo_name == "simpo"
    assert "trl>=0.12" in str(err)


# ---------------------------------------------------------------------------
# End-to-end via km.rl_train (behavioural, not grep)
# ---------------------------------------------------------------------------


def test_km_rl_train_dispatch_to_bridge_unregistered_raises_feature_not_available() -> (
    None
):
    """Calling ``km.rl_train(algo="dpo", ...)`` with no bridge registered
    AND kailash-align not importable MUST surface
    ``FeatureNotAvailableError`` with the ``[rl-bridge]`` message.

    Exercises the real dispatcher entry point — proves the classical-
    first-then-bridge routing in ``_rl_train.rl_train`` actually rides
    through ``resolve_bridge_adapter``.
    """
    from kailash_ml.rl import rl_train

    with patch(
        "kailash_ml.rl.align_adapter.importlib.import_module",
        side_effect=ImportError("No module named 'kailash_align.rl_bridge'"),
    ):
        with pytest.raises(FeatureNotAvailableError) as exc_info:
            rl_train(
                "text:preferences",
                algo="dpo",
                total_timesteps=1,
                preference_dataset={"fake": "dataset"},
            )

    assert exc_info.value.algo_name == "dpo"
    assert "kailash-align[rl-bridge]" in str(exc_info.value)


def test_km_rl_train_dpo_missing_preference_dataset_raises_value_error() -> None:
    """Spec §3.3: missing required bridge kwarg raises ``ValueError``
    with actionable message — not silent fallback.

    Registering a no-op bridge adapter lets us reach the kwarg-
    validation step without needing kailash-align installed.
    """
    from kailash_ml.rl import rl_train

    class _NoopDPO:
        name = "dpo"
        paradigm = "rlhf"
        buffer_kind = "preference"

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    snapshot = dict(BRIDGE_ADAPTERS)
    try:
        register_bridge_adapter("dpo", _NoopDPO)
        with pytest.raises(ValueError, match="preference_dataset"):
            rl_train(
                "text:preferences",
                algo="dpo",
                total_timesteps=1,
                # preference_dataset intentionally omitted
            )
    finally:
        BRIDGE_ADAPTERS.clear()
        BRIDGE_ADAPTERS.update(snapshot)
