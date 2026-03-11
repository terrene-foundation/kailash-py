"""Nexus connection interface for Kaizen agents."""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class NexusConnection:
    """
    Connection interface between Kaizen and Nexus.

    Provides:
    - Nexus platform lifecycle management
    - Workflow registration and management
    - Health monitoring
    - Multi-agent coordination
    """

    nexus_app: "Nexus"
    auto_discovery: bool = False

    def __post_init__(self):
        """Initialize connection to Nexus platform."""
        self._connected = True
        self._workflows = {}

    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self._connected

    def health_check(self) -> Dict[str, Any]:
        """Get health status of Nexus platform."""
        return {
            "status": "healthy" if self._connected else "disconnected",
            "workflows": len(self._workflows),
            "nexus_version": getattr(self.nexus_app, "__version__", "unknown"),
        }

    def register_workflow(self, name: str, workflow: Any) -> str:
        """Register a Kaizen workflow with Nexus."""
        self.nexus_app.register(name, workflow)
        self._workflows[name] = workflow
        return name

    def list_workflows(self) -> list[str]:
        """List all registered workflows."""
        return list(self._workflows.keys())

    def start(self, **kwargs):
        """Start Nexus platform."""
        return self.nexus_app.start(**kwargs)

    def stop(self):
        """Stop Nexus platform."""
        self._connected = False
        if hasattr(self.nexus_app, "stop"):
            return self.nexus_app.stop()
