# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests — km.rl_train entry point plumbing.

Covers W29 invariant #3 (module-level rl_train exists + is reachable
via ``from kailash_ml.rl import rl_train``) without actually training a
policy (that's the Tier-2 wiring test).
"""
from __future__ import annotations

import pytest

from kailash_ml.errors import RLError


class TestRLTrainImportability:
    def test_import_from_rl_package(self) -> None:
        from kailash_ml.rl import rl_train

        assert callable(rl_train)

    def test_import_from_module(self) -> None:
        from kailash_ml.rl._rl_train import rl_train

        assert callable(rl_train)


class TestRLTrainInputValidation:
    """rl_train rejects bad inputs with RLError (not ValueError)."""

    def test_zero_timesteps_raises_rl_error(self) -> None:
        from kailash_ml.rl import rl_train

        with pytest.raises(RLError, match="invalid_total_timesteps"):
            rl_train("CartPole-v1", algo="ppo", total_timesteps=0)

    def test_negative_timesteps_raises_rl_error(self) -> None:
        from kailash_ml.rl import rl_train

        with pytest.raises(RLError, match="invalid_total_timesteps"):
            rl_train("CartPole-v1", algo="ppo", total_timesteps=-5)

    def test_unknown_algo_surfaces_as_rl_error(self) -> None:
        """rl_train dispatches through the adapter registry, which raises
        RLError(reason='unknown_algorithm'). The error MUST propagate
        before any SB3 touch.
        """
        from kailash_ml.rl import rl_train

        with pytest.raises(RLError, match="unknown_algorithm"):
            # Use total_timesteps>0 so we get past the validation guard
            # and exercise the adapter dispatch path.
            rl_train("CartPole-v1", algo="bogus-unheard-of-algo", total_timesteps=1)
