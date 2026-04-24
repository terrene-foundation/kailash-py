# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.a regression — ambient-run gate per ``specs/ml-autolog.md §6.1``.

Guards against a future silent-no-op regression. Every competitor
(MLflow, Comet, Neptune, ClearML, W&B) silently skips when no run is
active; Kailash MUST raise :class:`AutologNoAmbientRunError`.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from kailash.ml.errors import AutologNoAmbientRunError
from kailash_ml.autolog import autolog


@pytest.mark.regression
async def test_autolog_outside_track_raises_loudly() -> None:
    """``async with km.autolog():`` outside ``km.track()`` raises
    :class:`AutologNoAmbientRunError`.
    """
    # Patch at the source module so the lazy import inside autolog()
    # picks up the mock.
    with patch("kailash_ml.tracking.get_current_run", return_value=None):
        with pytest.raises(AutologNoAmbientRunError, match="outside km.track"):
            async with autolog():
                pass  # pragma: no cover — MUST NOT reach


@pytest.mark.regression
async def test_autolog_error_message_names_remediation() -> None:
    """The error message MUST tell the user how to fix it (§6.1)."""
    with patch("kailash_ml.tracking.get_current_run", return_value=None):
        with pytest.raises(AutologNoAmbientRunError) as excinfo:
            async with autolog():
                pass  # pragma: no cover
    msg = str(excinfo.value)
    assert "km.track" in msg
    assert "km.autolog" in msg
