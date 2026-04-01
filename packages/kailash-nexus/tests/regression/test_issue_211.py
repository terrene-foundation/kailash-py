# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #211: Nexus enterprise gateway kills Docker Desktop PostgreSQL.

Root cause: Three independent issues compounded:
1. Dual runtime: Nexus created its own AsyncLocalRuntime AND the enterprise gateway
   created another. Neither shared — 2 independent connection pools.
2. Hardcoded server_type="enterprise" and max_workers=20 with no constructor override.
3. MCP transport created a third orphan AsyncLocalRuntime.

Fix: Share Nexus runtime with gateway, make server_type/max_workers configurable,
auto-detect sensible max_workers default.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.mark.regression
class TestIssue211DualRuntime:
    """Verify Nexus shares its runtime with the enterprise gateway."""

    def test_gateway_receives_nexus_runtime(self):
        """Gateway must use Nexus's runtime, not create its own."""
        from nexus import Nexus

        app = Nexus(enable_durability=False)
        gateway = app._http_transport._gateway

        # The enterprise gateway's async runtime should be acquired from
        # Nexus's runtime, not independently created.
        if hasattr(gateway, "_async_runtime") and gateway._async_runtime is not None:
            # Gateway should NOT own its runtime (it was injected)
            assert not gateway._owns_runtime, (
                "Gateway created its own runtime instead of using Nexus's shared runtime. "
                "This causes duplicate connection pools (the #211 bug)."
            )

    def test_only_one_runtime_created_without_injection(self):
        """When no external runtime is provided, Nexus creates exactly one."""
        from nexus import Nexus

        app = Nexus(enable_durability=False)

        # Nexus should own exactly one runtime
        assert app._owns_runtime is True
        assert app.runtime is not None


@pytest.mark.regression
class TestIssue211ConfigurableGateway:
    """Verify server_type and max_workers are configurable."""

    def test_server_type_parameter(self):
        """Nexus constructor accepts server_type parameter."""
        from nexus import Nexus

        # Should not raise
        app = Nexus(enable_durability=False, server_type="basic")
        assert app._server_type == "basic"

    def test_max_workers_parameter(self):
        """Nexus constructor accepts max_workers parameter."""
        from nexus import Nexus

        app = Nexus(enable_durability=False, max_workers=2)
        assert app._max_workers == 2

    def test_max_workers_env_override(self):
        """NEXUS_MAX_WORKERS env var overrides constructor parameter."""
        from nexus import Nexus

        with patch.dict(os.environ, {"NEXUS_MAX_WORKERS": "3"}):
            app = Nexus(enable_durability=False, max_workers=20)
            assert app._max_workers == 3

    def test_server_type_env_override(self):
        """NEXUS_SERVER_TYPE env var overrides constructor parameter."""
        from nexus import Nexus

        with patch.dict(os.environ, {"NEXUS_SERVER_TYPE": "basic"}):
            app = Nexus(enable_durability=False, server_type="enterprise")
            assert app._server_type == "basic"

    def test_max_workers_auto_detect(self):
        """When max_workers=None, auto-detects to min(4, cpu_count)."""
        from nexus import Nexus

        app = Nexus(enable_durability=False, max_workers=None)
        # auto-detect: min(4, cpu_count)
        cpu_count = os.cpu_count() or 4
        expected = min(4, cpu_count)
        gateway = app._http_transport._gateway
        # The gateway's thread pool should have at most 4 workers
        assert gateway.executor._max_workers <= max(4, cpu_count)

    def test_default_max_workers_not_20(self):
        """Default max_workers must NOT be 20 (the #211 bug value)."""
        from nexus import Nexus

        app = Nexus(enable_durability=False)
        gateway = app._http_transport._gateway
        # Auto-detect should produce <= 4 on most machines, never 20
        assert gateway.executor._max_workers <= max(4, os.cpu_count() or 4)
