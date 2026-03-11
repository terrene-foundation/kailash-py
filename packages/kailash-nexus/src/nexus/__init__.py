"""Kailash Nexus - Zero-Config Multi-Channel Workflow Platform.

Deploy Kailash workflows across API, CLI, and MCP channels with built-in
middleware, CORS, plugins, and preset configurations.

Usage:
    from nexus import Nexus

    # Simple case with CORS
    app = Nexus(cors_origins=["http://localhost:3000"])
    app.register("my_workflow", workflow.build())
    app.start()

    # With preset (one-line middleware stack)
    app = Nexus(preset="lightweight", cors_origins=["http://localhost:3000"])
    app.start()

    # Enterprise features
    app = Nexus(
        preset="saas",
        cors_origins=["https://app.example.com"],
        enable_auth=True,
        enable_monitoring=True,
    )
    app.start()
"""

from .core import MiddlewareInfo, Nexus, NexusPluginProtocol, RouterInfo, create_nexus
from .presets import PRESETS, NexusConfig, PresetConfig, apply_preset, get_preset

__version__ = "1.4.2"
__all__ = [
    # Core
    "Nexus",
    "create_nexus",
    # Middleware API
    "MiddlewareInfo",
    "RouterInfo",
    "NexusPluginProtocol",
    # Preset System
    "NexusConfig",
    "PresetConfig",
    "PRESETS",
    "get_preset",
    "apply_preset",
]
