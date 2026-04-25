# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for kailash-kaizen 2.13.1.

2.13.0 shipped with `kaizen/orchestration/__init__.py` unconditionally
importing `kaizen_agents.patterns.patterns` — but `kaizen-agents` is not a
declared dependency of `kailash-kaizen`. Clean-venv installs of the
package raised `ModuleNotFoundError` at module load. The 2.13.1 patch
guards the proxy import in a `try/except ImportError`.

This test verifies that `from kaizen.orchestration import OrchestrationRuntime`
succeeds even when `kaizen_agents` cannot be located.
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.mark.regression
def test_orchestration_imports_without_kaizen_agents(monkeypatch):
    """Reload `kaizen.orchestration` with `kaizen_agents` blocked from import.

    The proxy aliases MUST be skipped silently; OrchestrationRuntime and the
    accompanying public surface MUST still be importable.
    """
    # Drop any cached kaizen_agents modules + the orchestration module so
    # the reload re-executes the guard branch.
    for name in list(sys.modules):
        if name == "kaizen_agents" or name.startswith("kaizen_agents."):
            sys.modules.pop(name, None)
        if name == "kaizen.orchestration" or name.startswith("kaizen.orchestration."):
            sys.modules.pop(name, None)

    # Block kaizen_agents at the importer level — any attempt to import
    # MUST raise ImportError so the guard is exercised.
    real_import = (
        __builtins__["__import__"]
        if isinstance(__builtins__, dict)
        else __builtins__.__import__
    )

    def _blocked_import(name, *args, **kwargs):
        if name == "kaizen_agents" or name.startswith("kaizen_agents."):
            raise ImportError(f"blocked for regression test: {name}")
        return real_import(name, *args, **kwargs)

    if isinstance(__builtins__, dict):
        monkeypatch.setitem(__builtins__, "__import__", _blocked_import)
    else:
        monkeypatch.setattr(__builtins__, "__import__", _blocked_import)

    # Trigger the guard branch.
    orch_module = importlib.import_module("kaizen.orchestration")

    # The new public surface from #602 MUST still be reachable.
    assert hasattr(orch_module, "OrchestrationRuntime")
    assert hasattr(orch_module, "OrchestrationStrategy")
    assert hasattr(orch_module, "OrchestrationResult")
    assert hasattr(orch_module, "Coordinator")

    # The legacy proxy aliases MUST NOT be present when kaizen_agents is
    # unavailable — they are the optional surface.
    assert "kaizen.orchestration.patterns" not in sys.modules
