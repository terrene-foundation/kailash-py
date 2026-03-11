"""
Mock Nexus components for testing without Nexus installed.

These mocks simulate Nexus platform behavior for testing purposes.
"""

from typing import Any, Dict, Optional


class MockNexus:
    """
    Mock Nexus platform for testing.

    Simulates Nexus API for testing Kaizen-Nexus integration
    without requiring actual Nexus installation.
    """

    __version__ = "1.0.0-mock"

    def __init__(self, auto_discovery: bool = False, **kwargs):
        """Initialize mock Nexus instance."""
        self.auto_discovery = auto_discovery
        self._workflows: Dict[str, Any] = {}
        self._running: bool = False
        self._config = kwargs

    def register(self, name: str, workflow: Any) -> None:
        """
        Register a workflow with Nexus.

        Args:
            name: Workflow name
            workflow: Workflow instance (usually WorkflowBuilder.build() result)
        """
        self._workflows[name] = workflow

    def start(self, blocking: bool = True, **kwargs) -> Dict[str, Any]:
        """
        Start Nexus platform (mock).

        Args:
            blocking: Whether to block (ignored in mock)
            **kwargs: Additional start parameters

        Returns:
            Status dictionary
        """
        self._running = True
        return {
            "status": "started",
            "workflows": len(self._workflows),
            "blocking": blocking,
        }

    def stop(self) -> None:
        """Stop Nexus platform (mock)."""
        self._running = False

    def health_check(self) -> Dict[str, Any]:
        """
        Get platform health status (mock).

        Returns:
            Health status dictionary
        """
        return {
            "status": "healthy" if self._running else "stopped",
            "workflows": len(self._workflows),
            "version": self.__version__,
        }

    def list_workflows(self) -> list[str]:
        """
        List registered workflows.

        Returns:
            List of workflow names
        """
        return list(self._workflows.keys())

    def get_workflow(self, name: str) -> Optional[Any]:
        """
        Get workflow by name.

        Args:
            name: Workflow name

        Returns:
            Workflow instance or None
        """
        return self._workflows.get(name)
