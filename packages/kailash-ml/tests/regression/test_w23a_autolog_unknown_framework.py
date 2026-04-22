# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.a regression — unknown-framework + unknown-disable loud failure.

``specs/ml-autolog.md §4.2`` + §4.3: silent skip of typos is BLOCKED.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from kailash.ml.errors import AutologUnknownFrameworkError
from kailash_ml.autolog import autolog


@pytest.mark.regression
async def test_autolog_explicit_unknown_framework_raises() -> None:
    """``km.autolog("not_a_framework")`` raises
    :class:`AutologUnknownFrameworkError`."""
    ambient = SimpleNamespace(run_id="run-regression")
    with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
        with pytest.raises(AutologUnknownFrameworkError, match="not_a_framework"):
            async with autolog("not_a_framework"):
                pass  # pragma: no cover


@pytest.mark.regression
async def test_autolog_disable_unknown_framework_raises() -> None:
    """``km.autolog(disable=["typo"])`` raises per §4.3 — silent accept
    of typos is BLOCKED.
    """
    ambient = SimpleNamespace(run_id="run-regression")
    with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
        with pytest.raises(AutologUnknownFrameworkError, match="typo"):
            async with autolog(disable=["typo"]):
                pass  # pragma: no cover


@pytest.mark.regression
async def test_autolog_unknown_framework_error_lists_registered_names() -> None:
    """The error message MUST enumerate the registered integrations so
    the user can see what they meant to type.
    """
    ambient = SimpleNamespace(run_id="run-regression")
    with patch("kailash_ml.tracking.get_current_run", return_value=ambient):
        with pytest.raises(AutologUnknownFrameworkError) as excinfo:
            async with autolog("nope"):
                pass  # pragma: no cover
    assert "registered integrations" in str(excinfo.value)
