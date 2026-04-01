# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NTR-004: BackgroundService ABC.

Tests the BackgroundService abstract base class and its integration
with the Nexus lifecycle (start/stop/health_check).
"""

from __future__ import annotations

import pytest

from nexus import Nexus
from nexus.background import BackgroundService


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class FakeService(BackgroundService):
    """Concrete BackgroundService for testing."""

    def __init__(self, svc_name: str = "test-service", healthy: bool = True):
        self._name = svc_name
        self._healthy = healthy
        self.started = False
        self.stopped = False

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def is_healthy(self) -> bool:
        return self._healthy


# ---------------------------------------------------------------------------
# BackgroundService ABC tests
# ---------------------------------------------------------------------------


class TestBackgroundServiceABC:
    """Tests for the BackgroundService abstract base class."""

    def test_cannot_instantiate_abc(self):
        """BackgroundService cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BackgroundService()

    def test_concrete_subclass_instantiates(self):
        svc = FakeService()
        assert svc.name == "test-service"

    def test_is_healthy(self):
        healthy_svc = FakeService(healthy=True)
        assert healthy_svc.is_healthy() is True
        unhealthy_svc = FakeService(healthy=False)
        assert unhealthy_svc.is_healthy() is False

    @pytest.mark.asyncio
    async def test_start_stop(self):
        svc = FakeService()
        assert svc.started is False
        assert svc.stopped is False
        await svc.start()
        assert svc.started is True
        await svc.stop()
        assert svc.stopped is True

    def test_requires_all_abstract_methods(self):
        """Subclass missing any abstract method cannot be instantiated."""

        class Incomplete(BackgroundService):
            @property
            def name(self) -> str:
                return "inc"

            async def start(self):
                pass

            # Missing stop() and is_healthy()

        with pytest.raises(TypeError):
            Incomplete()


# ---------------------------------------------------------------------------
# Nexus integration tests
# ---------------------------------------------------------------------------


class TestNexusBackgroundServiceIntegration:
    """Tests for BackgroundService integration with Nexus."""

    def test_add_background_service(self):
        """Background services are registered on the Nexus instance."""
        with Nexus(enable_durability=False) as app:
            svc = FakeService("svc-1")
            result = app.add_background_service(svc)
            assert result is app  # Chaining
            assert len(app._background_services) == 1
            assert app._background_services[0] is svc

    def test_multiple_services(self):
        with Nexus(enable_durability=False) as app:
            svc1 = FakeService("svc-1")
            svc2 = FakeService("svc-2")
            app.add_background_service(svc1).add_background_service(svc2)
            assert len(app._background_services) == 2

    def test_health_check_includes_background_services(self):
        """health_check() reports background service health."""
        with Nexus(enable_durability=False) as app:
            healthy_svc = FakeService("healthy-svc", healthy=True)
            unhealthy_svc = FakeService("unhealthy-svc", healthy=False)
            app.add_background_service(healthy_svc)
            app.add_background_service(unhealthy_svc)

            health = app.health_check()
            assert "background_services" in health
            assert health["background_services"]["healthy-svc"] is True
            assert health["background_services"]["unhealthy-svc"] is False

    def test_health_check_no_background_key_when_empty(self):
        """health_check() omits background_services when none are registered."""
        with Nexus(enable_durability=False) as app:
            health = app.health_check()
            assert "background_services" not in health
