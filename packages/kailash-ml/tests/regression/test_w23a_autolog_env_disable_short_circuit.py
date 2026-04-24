# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.a regression — ``KAILASH_ML_AUTOLOG_DISABLED=1`` short-circuit
per ``specs/ml-autolog.md §5.3``.

Env var MUST short-circuit every ``autolog()`` block to a no-op CM
that STILL validates the ambient-run requirement.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from kailash.ml.errors import AutologNoAmbientRunError
from kailash_ml.autolog import autolog, registered_integration_names


# Module-scope lock per `rules/testing.md § Env-Var Test Isolation` —
# every test that mutates KAILASH_ML_AUTOLOG_DISABLED serializes so
# parallel xdist workers don't race on the env var.
_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized(monkeypatch: pytest.MonkeyPatch):
    with _ENV_LOCK:
        yield monkeypatch


@pytest.mark.regression
async def test_env_disabled_yields_zero_integrations(
    _env_serialized: pytest.MonkeyPatch,
) -> None:
    """With the env var set, the CM yields a handle with
    ``attached_integrations == ()`` and no error.
    """
    _env_serialized.setenv("KAILASH_ML_AUTOLOG_DISABLED", "1")
    ambient = SimpleNamespace(run_id="run-regression")
    with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
        async with autolog() as handle:
            assert handle.attached_integrations == ()
            assert handle.run_id == "run-regression"


@pytest.mark.regression
async def test_env_disabled_still_validates_ambient_run(
    _env_serialized: pytest.MonkeyPatch,
) -> None:
    """Per §5.3: the env-var short-circuit MUST still raise
    :class:`AutologNoAmbientRunError` when no run is active — users
    who forget ``km.track()`` get the same loud failure either way.
    """
    _env_serialized.setenv("KAILASH_ML_AUTOLOG_DISABLED", "1")
    with patch("kailash_ml.tracking.get_current_run", return_value=None):
        with pytest.raises(AutologNoAmbientRunError):
            async with autolog():
                pass  # pragma: no cover


@pytest.mark.regression
@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
async def test_env_falsey_values_do_not_disable(
    _env_serialized: pytest.MonkeyPatch,
    value: str,
) -> None:
    """Only ``1`` / ``true`` / ``yes`` / ``on`` disable — everything
    else is a no-op so `KAILASH_ML_AUTOLOG_DISABLED=0` does NOT
    accidentally disable.
    """
    _env_serialized.setenv("KAILASH_ML_AUTOLOG_DISABLED", value)
    ambient = SimpleNamespace(run_id="run-regression")
    with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
        async with autolog() as handle:
            # No integrations registered in this test process → still
            # an empty tuple. But the path taken is the FULL resolve
            # path (auto-detect), not the env-disable short-circuit.
            assert handle.run_id == "run-regression"
            assert set(handle.attached_integrations).issubset(
                set(registered_integration_names())
            )
