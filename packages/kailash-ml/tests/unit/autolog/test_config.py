# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.a unit tests — :class:`AutologConfig` + :class:`AutologHandle`.

Covers the §4.0 dataclass contract: frozen-ness, defaults, range-check
on ``tokens_per_second_window``, handle shape, :meth:`stop` idempotency.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kailash_ml.autolog import AutologConfig, AutologHandle


class TestAutologConfigDefaults:
    """Defaults MUST match ``specs/ml-autolog.md §2.1`` + §4.0."""

    def test_default_frameworks_is_auto_sentinel(self) -> None:
        cfg = AutologConfig()
        assert cfg.frameworks == ("auto",)

    def test_default_log_models_true(self) -> None:
        assert AutologConfig().log_models is True

    def test_default_log_datasets_true(self) -> None:
        assert AutologConfig().log_datasets is True

    def test_default_log_figures_true(self) -> None:
        assert AutologConfig().log_figures is True

    def test_default_log_system_metrics_false(self) -> None:
        # Off by default per §2.1 — psutil cost avoided.
        assert AutologConfig().log_system_metrics is False

    def test_default_system_metrics_interval_is_5s(self) -> None:
        # Phase-B SAFE-DEFAULT A-05.
        assert AutologConfig().system_metrics_interval_s == 5

    def test_default_sample_rate_is_1(self) -> None:
        assert AutologConfig().sample_rate_steps == 1

    def test_default_disable_is_empty_tuple(self) -> None:
        assert AutologConfig().disable == ()

    def test_default_disable_metrics_is_empty_tuple(self) -> None:
        assert AutologConfig().disable_metrics == ()

    def test_default_tokens_per_second_window_is_128(self) -> None:
        # Spec §3.1.2: 128 is the smallest window where prefill
        # artifacts wash out.
        assert AutologConfig().tokens_per_second_window == 128


class TestAutologConfigFrozen:
    """Config MUST be frozen — §4.0 MUST."""

    def test_config_frozen_cannot_mutate_frameworks(self) -> None:
        cfg = AutologConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.frameworks = ("lightning",)  # type: ignore[misc]

    def test_config_frozen_cannot_mutate_log_models(self) -> None:
        cfg = AutologConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.log_models = False  # type: ignore[misc]


class TestAutologConfigTokensPerSecondWindowValidation:
    """§3.1.2 MUST 2 — 8 ≤ window ≤ 4096."""

    def test_window_below_minimum_raises(self) -> None:
        with pytest.raises(ValueError, match="tokens_per_second_window"):
            AutologConfig(tokens_per_second_window=7)

    def test_window_above_maximum_raises(self) -> None:
        with pytest.raises(ValueError, match="tokens_per_second_window"):
            AutologConfig(tokens_per_second_window=4097)

    def test_window_at_boundaries_ok(self) -> None:
        # Inclusive boundaries per §3.1.2.
        AutologConfig(tokens_per_second_window=8)
        AutologConfig(tokens_per_second_window=4096)


class TestAutologHandleShape:
    """Handle's immutable view of the live block per §4.0."""

    def test_handle_captures_run_id(self) -> None:
        handle = AutologHandle(
            run_id="run-42",
            config=AutologConfig(),
            attached_integrations=("lightning",),
            _active=[],
        )
        assert handle.run_id == "run-42"

    def test_handle_attached_integrations_ordered_tuple(self) -> None:
        handle = AutologHandle(
            run_id="run-42",
            config=AutologConfig(),
            attached_integrations=("lightning", "sklearn"),
            _active=[],
        )
        assert handle.attached_integrations == ("lightning", "sklearn")

    def test_handle_frameworks_active_reads_live_list(self) -> None:
        """:attr:`frameworks_active` must reflect the mutable shared
        list the CM owns — NOT the frozen tuple.
        """
        from kailash_ml.autolog._registry import FrameworkIntegration

        class _Dummy(FrameworkIntegration):
            name = "dummy-active"

            @classmethod
            def is_available(cls) -> bool:
                return True

            def attach(self, run, config) -> None:  # type: ignore[override]
                pass

            def detach(self) -> None:  # type: ignore[override]
                pass

        live: list[FrameworkIntegration] = [_Dummy()]
        handle = AutologHandle(
            run_id="run-42",
            config=AutologConfig(),
            attached_integrations=("dummy-active",),
            _active=live,
        )
        assert handle.frameworks_active == ["dummy-active"]
        live.pop()
        # Post-stop, the live view is empty even though the frozen
        # attached_integrations still shows the original registration.
        assert handle.frameworks_active == []
        assert handle.attached_integrations == ("dummy-active",)

    def test_handle_stop_is_idempotent(self) -> None:
        """Calling :meth:`stop` twice is a no-op per §4.0 MUST."""
        handle = AutologHandle(
            run_id="run-42",
            config=AutologConfig(),
            attached_integrations=(),
            _active=[],
        )
        handle.stop()
        handle.stop()  # MUST NOT raise
