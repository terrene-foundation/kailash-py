# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Kubernetes probe endpoints for Nexus platform.

Provides liveness, readiness, and startup probe endpoints following
Kubernetes health check conventions. Thread-safe state management
with atomic transitions.

Usage:
    from nexus.probes import ProbeManager, ProbeState

    probes = ProbeManager()
    probes.mark_ready()

    # Mount on FastAPI/Starlette
    probes.install(app)

Endpoints:
    /healthz  - Liveness probe: 200 if process is alive
    /readyz   - Readiness probe: 200 when all workflows are ready
    /startup  - Startup probe: 200 after initialization complete
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ProbeState",
    "ProbeManager",
    "ProbeResponse",
]


class ProbeState(Enum):
    """Lifecycle state for Kubernetes probe management.

    State transitions are monotonic during normal operation:
        STARTING -> READY -> DRAINING

    FAILED can be reached from any state and is terminal
    (only manual intervention via reset() can recover).

    Allowed transitions:
        STARTING -> READY
        STARTING -> FAILED
        READY    -> DRAINING
        READY    -> FAILED
        DRAINING -> FAILED
    """

    STARTING = "starting"
    READY = "ready"
    DRAINING = "draining"
    FAILED = "failed"


# Valid state transitions (from -> set of allowed targets)
_VALID_TRANSITIONS: Dict[ProbeState, frozenset] = {
    ProbeState.STARTING: frozenset({ProbeState.READY, ProbeState.FAILED}),
    ProbeState.READY: frozenset({ProbeState.DRAINING, ProbeState.FAILED}),
    ProbeState.DRAINING: frozenset({ProbeState.FAILED}),
    ProbeState.FAILED: frozenset(),  # Terminal — use reset() to recover
}


@dataclass
class ProbeResponse:
    """Structured response from a probe check."""

    status: str
    http_status: int
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON response."""
        result: Dict[str, Any] = {
            "status": self.status,
        }
        if self.details:
            result["details"] = self.details
        return result


class ProbeManager:
    """Thread-safe Kubernetes probe manager.

    Manages liveness, readiness, and startup state for a Nexus instance.
    All state transitions are atomic and validated.

    Attributes:
        state: Current ProbeState (read via property).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = ProbeState.STARTING
        self._started_at = time.monotonic()
        self._ready_at: Optional[float] = None
        self._failed_reason: Optional[str] = None
        self._workflow_count = 0
        self._check_callbacks: List[Any] = []

    # -- State properties (read-only outside lock) ---

    @property
    def state(self) -> ProbeState:
        """Current probe state (thread-safe read)."""
        with self._lock:
            return self._state

    @property
    def is_alive(self) -> bool:
        """True if process is alive (not FAILED)."""
        with self._lock:
            return self._state != ProbeState.FAILED

    @property
    def is_ready(self) -> bool:
        """True if fully ready to serve traffic."""
        with self._lock:
            return self._state == ProbeState.READY

    @property
    def is_started(self) -> bool:
        """True if startup is complete (READY or DRAINING)."""
        with self._lock:
            return self._state in (ProbeState.READY, ProbeState.DRAINING)

    # -- State transitions ---

    def _transition(self, target: ProbeState, reason: Optional[str] = None) -> bool:
        """Atomically transition to a new state.

        Args:
            target: Target state.
            reason: Optional reason (used for FAILED state).

        Returns:
            True if transition succeeded, False if invalid.
        """
        with self._lock:
            allowed = _VALID_TRANSITIONS.get(self._state, frozenset())
            if target not in allowed:
                logger.warning(
                    "Invalid probe state transition: %s -> %s (allowed: %s)",
                    self._state.value,
                    target.value,
                    ", ".join(s.value for s in allowed) if allowed else "none",
                )
                return False

            old = self._state
            self._state = target

            if target == ProbeState.READY:
                self._ready_at = time.monotonic()
            elif target == ProbeState.FAILED:
                self._failed_reason = reason

            logger.info(
                "Probe state transition: %s -> %s%s",
                old.value,
                target.value,
                f" (reason: {reason})" if reason else "",
            )
            return True

    def mark_ready(self) -> bool:
        """Mark the instance as ready to serve traffic.

        Returns:
            True if transition succeeded.
        """
        return self._transition(ProbeState.READY)

    def mark_draining(self) -> bool:
        """Mark the instance as draining (graceful shutdown).

        Returns:
            True if transition succeeded.
        """
        return self._transition(ProbeState.DRAINING)

    def mark_failed(self, reason: str = "unknown") -> bool:
        """Mark the instance as failed.

        Args:
            reason: Human-readable failure reason.

        Returns:
            True if transition succeeded.
        """
        return self._transition(ProbeState.FAILED, reason=reason)

    def reset(self) -> None:
        """Reset to STARTING state (for recovery/testing).

        This is the only way to recover from FAILED state.
        """
        with self._lock:
            old = self._state
            self._state = ProbeState.STARTING
            self._ready_at = None
            self._failed_reason = None
            self._started_at = time.monotonic()
            logger.info("Probe state reset: %s -> STARTING", old.value)

    # -- Workflow tracking ---

    def set_workflow_count(self, count: int) -> None:
        """Update the registered workflow count.

        Args:
            count: Number of registered workflows.
        """
        with self._lock:
            self._workflow_count = count

    # -- Readiness check callbacks ---

    def add_readiness_check(self, callback: Any) -> None:
        """Register an additional readiness check callback.

        The callback should return True if the component is ready,
        False otherwise. Callbacks are invoked during readiness checks.

        Args:
            callback: Callable returning bool.
        """
        with self._lock:
            self._check_callbacks.append(callback)

    # -- Probe checks ---

    def check_liveness(self) -> ProbeResponse:
        """Check liveness (is the process alive?).

        Returns 200 for all states except FAILED.
        """
        with self._lock:
            alive = self._state != ProbeState.FAILED
            uptime = time.monotonic() - self._started_at

        if alive:
            return ProbeResponse(
                status="ok",
                http_status=200,
                details={"uptime_seconds": round(uptime, 2)},
            )

        return ProbeResponse(
            status="failed",
            http_status=503,
            details={
                "reason": self._failed_reason or "unknown",
                "uptime_seconds": round(uptime, 2),
            },
        )

    def check_readiness(self) -> ProbeResponse:
        """Check readiness (can the instance serve traffic?).

        Returns 200 only in READY state and all readiness callbacks pass.
        """
        with self._lock:
            ready = self._state == ProbeState.READY
            state_value = self._state.value
            wf_count = self._workflow_count
            callbacks = list(self._check_callbacks)

        if not ready:
            return ProbeResponse(
                status="not_ready",
                http_status=503,
                details={"state": state_value, "workflows": wf_count},
            )

        # Run readiness callbacks
        failed_checks: List[str] = []
        for cb in callbacks:
            try:
                if not cb():
                    name = getattr(cb, "__name__", str(cb))
                    failed_checks.append(name)
            except Exception as exc:
                name = getattr(cb, "__name__", str(cb))
                failed_checks.append(f"{name}: {exc}")

        if failed_checks:
            return ProbeResponse(
                status="not_ready",
                http_status=503,
                details={
                    "state": state_value,
                    "workflows": wf_count,
                    "failed_checks": failed_checks,
                },
            )

        return ProbeResponse(
            status="ready",
            http_status=200,
            details={"state": state_value, "workflows": wf_count},
        )

    def check_startup(self) -> ProbeResponse:
        """Check startup (has initialization completed?).

        Returns 200 once the instance has moved past STARTING state.
        """
        with self._lock:
            started = self._state in (ProbeState.READY, ProbeState.DRAINING)
            state_value = self._state.value
            uptime = time.monotonic() - self._started_at

        if started:
            return ProbeResponse(
                status="started",
                http_status=200,
                details={
                    "state": state_value,
                    "startup_duration_seconds": (
                        round(self._ready_at - self._started_at, 3)
                        if self._ready_at
                        else None
                    ),
                },
            )

        return ProbeResponse(
            status="starting",
            http_status=503,
            details={
                "state": state_value,
                "elapsed_seconds": round(uptime, 2),
            },
        )

    # -- FastAPI/Starlette integration ---

    def install(self, app: Any) -> None:
        """Install probe endpoints on a FastAPI or Starlette application.

        Adds /healthz, /readyz, and /startup routes.

        Args:
            app: FastAPI or Starlette application instance.
        """
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        probe_mgr = self

        async def healthz(request: Request) -> JSONResponse:
            resp = probe_mgr.check_liveness()
            return JSONResponse(resp.to_dict(), status_code=resp.http_status)

        async def readyz(request: Request) -> JSONResponse:
            resp = probe_mgr.check_readiness()
            return JSONResponse(resp.to_dict(), status_code=resp.http_status)

        async def startup(request: Request) -> JSONResponse:
            resp = probe_mgr.check_startup()
            return JSONResponse(resp.to_dict(), status_code=resp.http_status)

        routes = [
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readyz, methods=["GET"]),
            Route("/startup", startup, methods=["GET"]),
        ]

        # Support both FastAPI (include_router) and raw Starlette (routes.extend)
        if hasattr(app, "routes"):
            app.routes.extend(routes)
        else:
            logger.warning(
                "Unable to install probe routes: app has no 'routes' attribute"
            )

        logger.info("Kubernetes probe endpoints installed: /healthz, /readyz, /startup")
