"""Health check implementation for production monitoring.

Provides liveness, readiness, and startup probes for Kubernetes
and other orchestration platforms.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class DependencyCheck:
    """Configuration for a dependency health check."""

    name: str
    check_fn: Callable[[], bool]
    timeout: float = 5.0


class HealthCheck:
    """Production health check implementation.

    Provides three types of health probes:
    - Liveness: Is the process alive?
    - Readiness: Can the service handle requests?
    - Startup: Has the service started successfully?

    Example:
        >>> health = HealthCheck()
        >>> health.add_dependency("database", lambda: db.ping())
        >>> status = health.check()
        >>> print(status)
        {'status': 'healthy', 'dependencies': {...}}
    """

    def __init__(self):
        """Initialize health check system."""
        self._dependencies: Dict[str, DependencyCheck] = {}
        self._started = True  # Assume started by default
        self._ready = True  # Assume ready by default

    def add_dependency(
        self, name: str, check_fn: Callable[[], bool], timeout: float = 5.0
    ) -> None:
        """Add a dependency health check.

        Args:
            name: Dependency name (e.g., "database", "cache")
            check_fn: Function that returns True if healthy
            timeout: Timeout in seconds for the check
        """
        self._dependencies[name] = DependencyCheck(
            name=name, check_fn=check_fn, timeout=timeout
        )

    def liveness(self) -> Dict[str, Any]:
        """Check if the process is alive.

        Returns:
            Dict with 'alive' status
        """
        return {"alive": True, "status": "healthy", "timestamp": time.time()}

    def readiness(self) -> Dict[str, Any]:
        """Check if the service can handle requests.

        Returns:
            Dict with 'ready' status
        """
        return {
            "ready": self._ready,
            "status": "healthy" if self._ready else "not_ready",
            "timestamp": time.time(),
        }

    def startup(self) -> Dict[str, Any]:
        """Check if the service has started successfully.

        Returns:
            Dict with 'started' status
        """
        return {
            "started": self._started,
            "status": "healthy" if self._started else "starting",
            "timestamp": time.time(),
        }

    def check(self) -> Dict[str, Any]:
        """Perform comprehensive health check including dependencies.

        Returns:
            Dict with overall status and dependency details
        """
        result = {"status": "healthy", "timestamp": time.time(), "dependencies": {}}

        # Check all dependencies
        for name, dep_check in self._dependencies.items():
            dep_status = self._check_dependency(dep_check)
            result["dependencies"][name] = dep_status

            # If any dependency is unhealthy, mark overall as unhealthy
            if dep_status["status"] == "unhealthy":
                result["status"] = "unhealthy"
            elif dep_status["status"] == "timeout" and result["status"] == "healthy":
                result["status"] = "degraded"

        return result

    def _check_dependency(self, dep_check: DependencyCheck) -> Dict[str, Any]:
        """Check a single dependency with timeout.

        Args:
            dep_check: Dependency configuration

        Returns:
            Dict with dependency status
        """
        result = {"status": "healthy", "timestamp": time.time()}

        # Use threading to implement timeout
        check_result = {"success": False, "error": None}

        def run_check():
            try:
                check_result["success"] = dep_check.check_fn()
            except Exception as e:
                check_result["error"] = str(e)

        thread = threading.Thread(target=run_check, daemon=True)
        thread.start()
        thread.join(timeout=dep_check.timeout)

        if thread.is_alive():
            # Timeout occurred
            result["status"] = "timeout"
            result["error"] = f"Check timed out after {dep_check.timeout}s"
        elif check_result["error"]:
            # Exception occurred
            result["status"] = "unhealthy"
            result["error"] = check_result["error"]
        elif not check_result["success"]:
            # Check returned False
            result["status"] = "unhealthy"
        else:
            # Check passed
            result["status"] = "healthy"

        return result

    def set_ready(self, ready: bool) -> None:
        """Set readiness status.

        Args:
            ready: True if service is ready to handle requests
        """
        self._ready = ready

    def set_started(self, started: bool) -> None:
        """Set startup status.

        Args:
            started: True if service has completed startup
        """
        self._started = started
