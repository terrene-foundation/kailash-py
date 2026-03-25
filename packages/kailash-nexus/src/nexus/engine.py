# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""NexusEngine — unified gateway with builder pattern.

Wraps the Nexus primitive with enterprise middleware presets, bind address
configuration, and a fluent builder API. Matches the kailash-rs NexusEngine
API surface for cross-SDK parity.

Usage:
    from nexus import NexusEngine, Preset

    # Zero-config
    engine = NexusEngine.builder().build()

    # SaaS preset
    engine = NexusEngine.builder().preset(Preset.SAAS).bind("0.0.0.0:8080").build()

    # Enterprise with full middleware
    engine = (
        NexusEngine.builder()
        .preset(Preset.ENTERPRISE)
        .bind("0.0.0.0:443")
        .build()
    )

    # Access underlying Nexus for handler registration
    engine.nexus.register("my_workflow", workflow.build())
    engine.start()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from nexus.core import Nexus

logger = logging.getLogger(__name__)


class Preset(Enum):
    """Middleware preset configurations matching kailash-rs Preset enum."""

    NONE = "none"
    SAAS = "saas"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class EnterpriseMiddlewareConfig:
    """Enterprise middleware configuration.

    Controls which enterprise features are enabled in the NexusEngine.
    """

    enable_csrf: bool = True
    enable_audit: bool = True
    enable_metrics: bool = True
    enable_error_handler: bool = True
    enable_security_headers: bool = True
    enable_structured_logging: bool = True
    enable_rate_limiting: bool = True
    rate_limit_rpm: int = 100
    enable_cors: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])


def _config_from_preset(preset: Preset) -> Optional[EnterpriseMiddlewareConfig]:
    """Generate enterprise middleware config from a preset."""
    if preset == Preset.NONE:
        return None
    elif preset == Preset.SAAS:
        return EnterpriseMiddlewareConfig(
            enable_csrf=False,
            enable_audit=False,
            enable_metrics=True,
            enable_error_handler=True,
            enable_security_headers=True,
            enable_structured_logging=True,
            enable_rate_limiting=True,
            rate_limit_rpm=200,
        )
    elif preset == Preset.ENTERPRISE:
        return EnterpriseMiddlewareConfig(
            enable_csrf=True,
            enable_audit=True,
            enable_metrics=True,
            enable_error_handler=True,
            enable_security_headers=True,
            enable_structured_logging=True,
            enable_rate_limiting=True,
            rate_limit_rpm=100,
        )
    return None


class NexusEngineBuilder:
    """Fluent builder for NexusEngine. Matches kailash-rs NexusEngineBuilder API."""

    def __init__(self) -> None:
        self._preset: Preset = Preset.NONE
        self._enterprise_config: Optional[EnterpriseMiddlewareConfig] = None
        self._bind_addr: str = "0.0.0.0:3000"
        self._nexus_kwargs: Dict[str, Any] = {}

    def preset(self, preset: Preset) -> NexusEngineBuilder:
        """Set a middleware preset (NONE, SAAS, ENTERPRISE)."""
        self._preset = preset
        return self

    def enterprise(self, config: EnterpriseMiddlewareConfig) -> NexusEngineBuilder:
        """Set explicit enterprise middleware configuration (overrides preset)."""
        self._enterprise_config = config
        return self

    def bind(self, addr: str) -> NexusEngineBuilder:
        """Set the bind address (e.g., '0.0.0.0:8080')."""
        self._bind_addr = addr
        return self

    def config(self, **kwargs: Any) -> NexusEngineBuilder:
        """Pass additional configuration to the underlying Nexus instance."""
        self._nexus_kwargs.update(kwargs)
        return self

    def build(self) -> NexusEngine:
        """Build the NexusEngine instance."""
        # Resolve enterprise config: explicit > preset
        enterprise_config = self._enterprise_config or _config_from_preset(self._preset)

        # Parse bind address
        host, _, port_str = self._bind_addr.rpartition(":")
        api_port = int(port_str) if port_str else 3000
        if not host:
            host = "0.0.0.0"

        # Build Nexus kwargs from enterprise config
        nexus_kwargs = dict(self._nexus_kwargs)
        nexus_kwargs.setdefault("api_port", api_port)
        if enterprise_config:
            nexus_kwargs.setdefault(
                "preset",
                self._preset.value if self._preset != Preset.NONE else "enterprise",
            )
            nexus_kwargs.setdefault(
                "enable_monitoring", enterprise_config.enable_metrics
            )
            if enterprise_config.enable_rate_limiting:
                nexus_kwargs.setdefault("rate_limit", enterprise_config.rate_limit_rpm)
            if enterprise_config.enable_cors:
                nexus_kwargs.setdefault("cors_origins", enterprise_config.cors_origins)

        nexus = Nexus(**nexus_kwargs)

        return NexusEngine(
            nexus=nexus,
            enterprise_config=enterprise_config,
            bind_addr=self._bind_addr,
        )


class NexusEngine:
    """Unified gateway wrapping Nexus with enterprise middleware.

    Provides a builder-pattern API matching kailash-rs NexusEngine for
    cross-SDK parity. Wraps the Nexus primitive with configuration presets
    and enterprise middleware.

    Use NexusEngine.builder() to create instances.
    """

    def __init__(
        self,
        nexus: Nexus,
        enterprise_config: Optional[EnterpriseMiddlewareConfig] = None,
        bind_addr: str = "0.0.0.0:3000",
    ) -> None:
        self._nexus = nexus
        self._enterprise_config = enterprise_config
        self._bind_addr = bind_addr

    @staticmethod
    def builder() -> NexusEngineBuilder:
        """Create a new NexusEngine builder."""
        return NexusEngineBuilder()

    @property
    def nexus(self) -> Nexus:
        """Read-only access to the underlying Nexus instance."""
        return self._nexus

    @property
    def bind_addr(self) -> str:
        """Get the configured bind address."""
        return self._bind_addr

    @property
    def enterprise_config(self) -> Optional[EnterpriseMiddlewareConfig]:
        """Get enterprise middleware config, if set."""
        return self._enterprise_config

    def register(self, name: str, workflow: Any, **kwargs: Any) -> None:
        """Register a workflow with the underlying Nexus instance."""
        self._nexus.register(name, workflow, **kwargs)

    def start(self, **kwargs: Any) -> None:
        """Start the NexusEngine (delegates to Nexus.start)."""
        self._nexus.start(**kwargs)

    async def start_async(self, **kwargs: Any) -> None:
        """Start the NexusEngine asynchronously."""
        await self._nexus.start_async(**kwargs)

    def close(self) -> None:
        """Close the NexusEngine and release resources."""
        if hasattr(self._nexus, "close"):
            self._nexus.close()
