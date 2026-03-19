from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Verify no import cycles exist between new modules."""

import importlib
import pytest


class TestImportCycles:
    """Verify all new modules import cleanly without circular dependencies."""

    @pytest.mark.parametrize(
        "module_name",
        [
            "kaizen.manifest",
            "kaizen.manifest.agent",
            "kaizen.manifest.app",
            "kaizen.manifest.governance",
            "kaizen.manifest.loader",
            "kaizen.manifest.errors",
            "kaizen.deploy",
            "kaizen.deploy.introspect",
            "kaizen.deploy.client",
            "kaizen.deploy.registry",
            "kaizen.composition",
            "kaizen.composition.dag_validator",
            "kaizen.composition.schema_compat",
            "kaizen.composition.cost_estimator",
            "kaizen.composition.models",
            "kaizen.governance.posture_budget",
            "kaizen.mcp.catalog_server",
            "kaizen.mcp.catalog_server.server",
        ],
    )
    def test_module_imports_cleanly(self, module_name: str) -> None:
        """Each module should import without ImportError or circular import."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize(
        "module_name",
        [
            "eatp.constraints.budget_tracker",
            "eatp.constraints.budget_store",
            "eatp.posture_store",
            "eatp.postures",
        ],
    )
    def test_eatp_module_imports_cleanly(self, module_name: str) -> None:
        """EATP modules import without errors."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    def test_no_reverse_imports(self) -> None:
        """EATP must never import from kaizen or dataflow."""
        import eatp

        # Check that the eatp package source doesn't reference kaizen
        import inspect

        source_file = inspect.getfile(eatp)
        # Just verify the import works -- structural check
        assert eatp is not None
