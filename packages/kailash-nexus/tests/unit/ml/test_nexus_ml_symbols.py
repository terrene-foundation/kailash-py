# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 tests: `nexus.ml` module surface presence (import + symbol check).

These tests guard the public contract of the ml-bridge module introduced in
kailash-nexus 2.2.0 (W31.c). They verify every symbol named in the spec is
present and callable / constructible — orphan-detection Rule 6 companion:
symbols advertised by the spec MUST be importable.
"""

from __future__ import annotations

import inspect

import pytest


class TestNexusMlSymbols:
    """Spec §1.1 items 3, 4 + §4 + spec "iframe integration helper"."""

    def test_module_imports(self):
        import nexus.ml as ml

        assert ml is not None

    def test_mldashboard_class_exists(self):
        from nexus.ml import MLDashboard

        assert inspect.isclass(MLDashboard)
        assert hasattr(MLDashboard, "from_nexus")
        assert hasattr(MLDashboard, "authenticate")

    def test_dashboard_principal_is_frozen(self):
        from nexus.ml import DashboardPrincipal

        p = DashboardPrincipal(actor_id="alice", tenant_id="t1", scopes=("read",))
        # @dataclass(frozen=True) — mutation raises FrozenInstanceError
        with pytest.raises(Exception):
            p.actor_id = "bob"  # type: ignore[misc]

    def test_mount_ml_endpoints_is_callable(self):
        from nexus.ml import mount_ml_endpoints

        assert callable(mount_ml_endpoints)
        sig = inspect.signature(mount_ml_endpoints)
        params = list(sig.parameters.keys())
        # Spec contract: mount_ml_endpoints(nexus, serve_handle, *, prefix)
        assert params[0] == "nexus"
        assert params[1] == "serve_handle"
        assert "prefix" in sig.parameters

    def test_dashboard_embed_returns_iframe_snippet(self):
        from nexus.ml import dashboard_embed

        snippet = dashboard_embed(8080)
        assert "<iframe" in snippet
        assert "8080" in snippet
        assert "sandbox=" in snippet

    def test_dashboard_embed_rejects_invalid_port(self):
        from nexus.ml import dashboard_embed

        with pytest.raises(ValueError, match="port"):
            dashboard_embed(0)
        with pytest.raises(ValueError, match="port"):
            dashboard_embed(70000)
        with pytest.raises(ValueError, match="port"):
            dashboard_embed("8080")  # type: ignore[arg-type]

    def test_all_exports(self):
        import nexus.ml as ml

        assert "MLDashboard" in ml.__all__
        assert "mount_ml_endpoints" in ml.__all__
        assert "dashboard_embed" in ml.__all__
        assert "DashboardPrincipal" in ml.__all__
