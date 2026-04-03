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
from .engine import EnterpriseMiddlewareConfig, NexusEngine, Preset
from .openapi import OpenApiGenerator, OpenApiInfo
from .presets import PRESETS, NexusConfig, PresetConfig, apply_preset, get_preset
from .background import BackgroundService
from .probes import ProbeManager, ProbeResponse, ProbeState
from .events import EventBus, NexusEvent, NexusEventType
from .files import NexusFile
from .registry import HandlerDef, HandlerParam, HandlerRegistry
from .transports import HTTPTransport, MCPTransport, Transport

__version__ = "1.7.2"
__all__ = [
    # Core
    "Nexus",
    "create_nexus",
    # Transport Layer
    "Transport",
    "HTTPTransport",
    "MCPTransport",
    # Handler Registry
    "HandlerDef",
    "HandlerParam",
    "HandlerRegistry",
    # Event System
    "EventBus",
    "NexusEvent",
    "NexusEventType",
    # Background Services
    "BackgroundService",
    # Files
    "NexusFile",
    # Engine (cross-SDK parity with kailash-rs)
    "NexusEngine",
    "Preset",
    "EnterpriseMiddlewareConfig",
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
    # Kubernetes Probes
    "ProbeManager",
    "ProbeState",
    "ProbeResponse",
    # OpenAPI
    "OpenApiGenerator",
    "OpenApiInfo",
]
