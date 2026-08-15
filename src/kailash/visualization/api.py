"""API endpoints for real-time dashboard data access.

This module provides REST API endpoints for accessing real-time workflow
performance data, metrics, and dashboard components for web-based interfaces.

Design Purpose:
- Provide RESTful API access to live performance metrics
- Enable real-time dashboard updates via HTTP endpoints
- Support WebSocket connections for streaming data
- Integrate with web dashboard frameworks and monitoring tools

Authentication (#2112):
``DashboardAPIServer`` builds its own FastAPI application and serves it under
its own uvicorn, so it is an HTTP server in its own right -- the SEVENTH
surface of the anonymous-access defect #2072, and the one PR #2100 did not
reach. It now resolves through :mod:`kailash.utils.server_auth` exactly as the
other six do: ``require_auth`` defaults to ``True`` and construction RAISES
:class:`~kailash.utils.server_auth.ServerAuthNotConfiguredError` when no
credential source is configured. ``SimpleDashboardAPI`` below is unaffected --
it opens no socket.

Upstream Dependencies:
- RealTimeDashboard provides live monitoring capabilities
- TaskManager provides workflow execution data
- WorkflowPerformanceReporter provides detailed analysis
- MetricsCollector provides performance metrics

Downstream Consumers:
- Web dashboard frontends consume these APIs
- Monitoring tools integrate via REST endpoints
- CI/CD systems access performance data
- Third-party analytics platforms
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskStatus
from kailash.utils.http_errors import safe_http_detail
from kailash.utils.secure_logging import safe_exception_frames, safe_type_name
from kailash.utils.server_auth import (
    install_server_auth_middleware,
    resolve_server_auth,
)
from kailash.visualization.dashboard import DashboardConfig, RealTimeDashboard
from kailash.visualization.reports import ReportFormat, WorkflowPerformanceReporter

# FastAPI is optional - import via importlib to avoid pyright errors on absent modules
_fastapi: Any = None
_fastapi_responses: Any = None
_fastapi_cors: Any = None
try:
    _fastapi = importlib.import_module("fastapi")
    _fastapi_responses = importlib.import_module("fastapi.responses")
    _fastapi_cors = importlib.import_module("fastapi.middleware.cors")
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Re-export names for use in function signatures and bodies
FastAPI: Any = getattr(_fastapi, "FastAPI", None)
HTTPException: Any = getattr(_fastapi, "HTTPException", None)

# `WebSocket` is the one re-export used in ANNOTATION position (the two
# `@self.app.websocket(...)` endpoints), and that makes the plain
# `WebSocket: Any = getattr(...)` form wrong in two directions at once:
#
#   * To a TYPE CHECKER a module-level variable is not a type expression, so
#     `websocket: WebSocket` is `reportInvalidTypeForm` -- measured, pyright
#     1.1.413 reported it at both endpoint definitions.
#   * To FASTAPI the annotation is load-bearing at RUNTIME. This module sets
#     `from __future__ import annotations`, so annotations are strings that
#     FastAPI resolves with `get_type_hints` against these module globals. A
#     bare `if TYPE_CHECKING: from fastapi import WebSocket` would therefore
#     leave the name UNDEFINED at runtime and raise `NameError` during route
#     registration -- and annotating it `Any` instead is what caused the
#     handshake defect this PR fixes (the socket is never bound and
#     `websocket` becomes a required QUERY PARAMETER; see the endpoint
#     docstrings).
#
# The split below satisfies both: the checker reads the real class from the
# `TYPE_CHECKING` import, and the runtime binds the same name via `getattr`,
# so `get_type_hints` resolves it exactly as before. `WebSocketDisconnect` is
# carried along as the paired name -- it is only used in `except` clauses
# today, but a real class there is checkable where `Any` is not.
if TYPE_CHECKING:  # pragma: no cover -- typing only
    from fastapi import WebSocket, WebSocketDisconnect
else:
    WebSocket = getattr(_fastapi, "WebSocket", None)
    WebSocketDisconnect = getattr(_fastapi, "WebSocketDisconnect", None)

BackgroundTasks: Any = getattr(_fastapi, "BackgroundTasks", None)
CORSMiddleware: Any = getattr(_fastapi_cors, "CORSMiddleware", None)
FileResponse: Any = getattr(_fastapi_responses, "FileResponse", None)

logger = logging.getLogger(__name__)

# How long the stop endpoint waits for the metrics broadcast task to actually
# finish before refusing to report it stopped. Bounded because this runs inside
# an HTTP handler; long enough that an ordinary iteration of the broadcast loop
# can reach its next cancellation point.
_BROADCAST_STOP_TIMEOUT_S = 5.0


# Pydantic models for API requests/responses
if FASTAPI_AVAILABLE:

    class RunRequest(BaseModel):
        """Request model for starting monitoring."""

        run_id: str | None = None
        config: dict[str, Any] | None = None

    class MetricsResponse(BaseModel):
        """Response model for metrics data."""

        timestamp: datetime
        active_tasks: int
        completed_tasks: int
        failed_tasks: int
        total_cpu_usage: float
        total_memory_usage: float
        throughput: float
        avg_task_duration: float

    class TaskResponse(BaseModel):
        """Response model for task data."""

        node_id: str
        node_type: str
        status: str
        started_at: datetime | None
        ended_at: datetime | None
        duration: float | None
        cpu_usage: float | None
        memory_usage_mb: float | None
        error_message: str | None

    class RunResponse(BaseModel):
        """Response model for run information."""

        run_id: str
        workflow_name: str
        status: str
        started_at: Any = None
        ended_at: Any = None
        total_tasks: int
        completed_tasks: int
        failed_tasks: int

    class ReportRequest(BaseModel):
        """Request model for generating reports."""

        run_id: str
        format: str = "html"
        include_charts: bool = True
        compare_runs: list[str] | None = None
        detail_level: str = "detailed"


class DashboardAPIServer:
    """FastAPI server for dashboard API endpoints.

    This class provides a complete REST API server for accessing real-time
    workflow performance data and dashboard components.

    Authentication fails CLOSED (#2112): ``require_auth`` defaults to ``True``
    and construction raises
    :class:`~kailash.utils.server_auth.ServerAuthNotConfiguredError` unless a
    credential source is configured.

    Usage:
        # export KAILASH_JWT_SECRET=<at least 32 bytes>
        api_server = DashboardAPIServer(task_manager)
        api_server.start_server(host="0.0.0.0", port=8000)

        # Or, to run without authentication -- an explicit opt-out that logs a
        # loud WARN naming the exposure:
        api_server = DashboardAPIServer(task_manager, require_auth=False)
    """

    def __init__(
        self,
        task_manager: TaskManager,
        dashboard_config: DashboardConfig | None = None,
        cors_origins: list[str] | None = None,
        # Server-wide authentication (#2112, the seventh surface of #2072).
        # NAMED parameters, never **kwargs -- `enable_auth=True` has shipped as
        # a swallowed kwarg twice (#2025, #2013), so the documented security
        # control did nothing. A named parameter makes that unexpressible: a
        # typo is a TypeError, not a silently open server.
        require_auth: bool = True,
        auth_config: Any = None,
        external_auth_reason: str | None = None,
        auth_exempt_paths: list[str] | None = None,
    ):
        """Initialize API server.

        Args:
            task_manager: TaskManager instance for data access
            dashboard_config: Configuration for dashboard components
            cors_origins: Allowed CORS origins. Defaults to ``[]`` (no
                cross-origin browser access), which is what this server has
                always used; supplying a list is what makes the CORS layer
                actually usable from a dashboard front-end.
            require_auth: Whether every request must be authenticated.
                **Defaults to ``True`` (fail-closed) and this is a BREAKING
                change** -- see :mod:`kailash.utils.server_auth`. This class
                builds its own FastAPI application and ships its own
                :meth:`start_server` under uvicorn, so it is a server in its
                own right: reachable without ``WorkflowServer``, without
                ``create_gateway()``, and untouched by the six surfaces PR
                #2100 closed. Un-gated it served ``GET /api/v1/runs``,
                ``GET /api/v1/runs/{id}/tasks``, report downloads and two
                websocket streams to anonymous callers -- run history and
                per-run task breakdowns describing what the system runs and
                when. There is no execute route here, so this is anonymous
                DISCLOSURE rather than anonymous code execution.

                Construction RAISES
                :class:`~kailash.utils.server_auth.ServerAuthNotConfiguredError`
                when no credential source is configured, rather than serving
                that surface openly. Set ``KAILASH_JWT_SECRET`` (or
                ``KAILASH_API_KEY_<NAME>``, or pass ``auth_config=``) to
                configure one. Pass ``require_auth=False`` to run without
                authentication -- an explicit opt-out that logs a loud WARN.
            auth_config: Explicit :class:`~kailash.trust.auth.jwt.JWTConfig`
                (or a ``dict`` of its fields) to authenticate with, bypassing
                environment lookup.
            external_auth_reason: Non-empty string declaring that an ASGI
                middleware OUTSIDE this server authenticates every request, so
                this server installs none. A blank string is rejected -- a
                reason that names nothing is an undocumented hole.
            auth_exempt_paths: Extra paths exempt from authentication, on top
                of the health-probe defaults. ``/docs``, ``/openapi.json`` and
                the ``/api/v1/*`` routes are NOT exempt by default; each
                describes or exposes the protected surface.

        Raises:
            ImportError: FastAPI is not installed.
            ServerAuthNotConfiguredError: ``require_auth=True`` and no
                credential source is configured.
        """
        if not FASTAPI_AVAILABLE:
            raise ImportError(
                "FastAPI is required for API server functionality. "
                "Install with: pip install fastapi uvicorn"
            )

        # Resolve authentication FIRST (#2112), before RealTimeDashboard and
        # WorkflowPerformanceReporter below are constructed. A raise afterwards
        # would strand whatever they hold, because __init__ never returns and
        # no caller ends up with a reference to release.
        self._auth_config = resolve_server_auth(
            require_auth=require_auth,
            auth_config=auth_config,
            external_auth_reason=external_auth_reason,
            extra_exempt_paths=auth_exempt_paths,
            server_label=f"{type(self).__name__}(title='Kailash Dashboard API')",
        )

        self.task_manager = task_manager
        self.dashboard_config = dashboard_config or DashboardConfig()

        # Initialize dashboard and reporter
        self.dashboard = RealTimeDashboard(task_manager, self.dashboard_config)
        self.reporter = WorkflowPerformanceReporter(task_manager)

        # WebSocket connections for real-time updates
        self._websocket_connections: list[Any] = []
        self._broadcast_task: asyncio.Task | None = None

        # Create FastAPI app
        self.app = FastAPI(
            title="Kailash Dashboard API",
            description="Real-time workflow performance monitoring API",
            version="1.0.0",
        )

        # Install authentication (#2112) -- middleware, and BEFORE CORS below.
        #
        # Starlette's `add_middleware` PREPENDS, so the LAST layer added is the
        # OUTERMOST one. Auth added after CORS would sit inside it and reject
        # cross-origin preflight OPTIONS with 401 before CORS could answer.
        #
        # Middleware rather than a route dependency, and specifically
        # `install_server_auth_middleware`, because this server registers TWO
        # `@app.websocket(...)` routes. `JWTAuthMiddleware` extends Starlette's
        # `BaseHTTPMiddleware`, whose `__call__` returns early for any scope
        # that is not "http", so its `dispatch` never runs for a websocket
        # handshake; the shared installer adds the websocket layer alongside it
        # so both routes are actually gated (#2100).
        #
        # `_auth_config` is None when authentication was explicitly declined or
        # declared external, in which case nothing is installed.
        if self._auth_config is not None:
            install_server_auth_middleware(self.app, self._auth_config)

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins or []),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register routes
        self._register_routes()

        self.logger = logger

    def _register_routes(self):
        """Register all API routes."""

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.now()}

        @self.app.get("/api/v1/runs", response_model=list[RunResponse])
        async def list_runs(limit: int = 10, offset: int = 0):
            """Get list of workflow runs."""
            try:
                all_runs = self.task_manager.list_runs()
                # Apply manual pagination
                runs = all_runs[offset : offset + limit]

                run_responses = []
                for run in runs:
                    tasks = self.task_manager.get_run_tasks(run.run_id)
                    completed_count = sum(
                        1 for t in tasks if t.status == TaskStatus.COMPLETED
                    )
                    failed_count = sum(
                        1 for t in tasks if t.status == TaskStatus.FAILED
                    )

                    run_responses.append(
                        RunResponse(
                            run_id=run.run_id,
                            workflow_name=run.workflow_name,
                            status=run.status,
                            started_at=run.started_at,
                            ended_at=run.ended_at,
                            total_tasks=len(tasks),
                            completed_tasks=completed_count,
                            failed_tasks=failed_count,
                        )
                    )

                return run_responses
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(e, logger=self.logger, context="list runs"),
                ) from e

        @self.app.get("/api/v1/runs/{run_id}", response_model=RunResponse)
        async def get_run(run_id: str):
            """Get details for a specific run."""
            try:
                run = self.task_manager.get_run(run_id)
                if not run:
                    raise HTTPException(status_code=404, detail="Run not found")

                tasks = self.task_manager.get_run_tasks(run_id)
                completed_count = sum(
                    1 for t in tasks if t.status == TaskStatus.COMPLETED
                )
                failed_count = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

                return RunResponse(
                    run_id=run.run_id,
                    workflow_name=run.workflow_name,
                    status=run.status,
                    started_at=run.started_at,
                    ended_at=run.ended_at,
                    total_tasks=len(tasks),
                    completed_tasks=completed_count,
                    failed_tasks=failed_count,
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(e, logger=self.logger, context="get run"),
                ) from e

        @self.app.get("/api/v1/runs/{run_id}/tasks", response_model=list[TaskResponse])
        async def get_run_tasks(run_id: str):
            """Get tasks for a specific run."""
            try:
                run = self.task_manager.get_run(run_id)
                if not run:
                    raise HTTPException(status_code=404, detail="Run not found")

                tasks = self.task_manager.get_run_tasks(run_id)

                task_responses = []
                for task in tasks:
                    task_responses.append(
                        TaskResponse(
                            node_id=task.node_id,
                            node_type=task.node_type,
                            status=task.status,
                            started_at=task.started_at,
                            ended_at=task.ended_at,
                            duration=task.metrics.duration if task.metrics else None,
                            cpu_usage=task.metrics.cpu_usage if task.metrics else None,
                            memory_usage_mb=(
                                task.metrics.memory_usage_mb if task.metrics else None
                            ),
                            error_message=task.error,
                        )
                    )

                return task_responses
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="get run tasks"
                    ),
                ) from e

        @self.app.post("/api/v1/monitoring/start")
        async def start_monitoring(request: RunRequest):
            """Start real-time monitoring for a run.

            Returns ``{"status": "started", ...}`` only when a metrics
            broadcast task is actually running afterwards -- either one that
            was already healthy, or a freshly created one.

            Responds 409 instead when a previous stop request did not complete
            and the broadcast task it could not stop is still alive. Nothing is
            mutated in that case; retry ``POST /api/v1/monitoring/stop`` first.
            """
            try:
                # A retained handle does NOT mean a task is broadcasting.
                #
                # ``stop_monitoring`` below deliberately KEEPS the handle when
                # the broadcast task refuses to stop -- it is the only thing
                # that can observe or retry that task. So the old
                # ``if not self._broadcast_task`` was false for a task nothing
                # had certified as stopped: no task was created and the
                # endpoint reported ``started`` over the very task the stop
                # endpoint had just returned 500 about.
                #
                # ``cancelling()`` is the discriminator between the two live
                # cases: a healthy broadcaster nobody has asked to stop reports
                # 0, while a task a failed stop cancelled and could not kill
                # reports >= 1. It is derived from the task itself, so it
                # cannot drift out of step the way a parallel flag would.
                #
                # Checked BEFORE anything is mutated. ``dashboard._monitoring``
                # is this task's own ``while`` condition (see
                # ``_broadcast_metrics``), so re-arming it and only then
                # refusing would leave a rejected request half-applied -- and
                # would hand the wedged task its loop condition back.
                existing = self._broadcast_task
                if existing is not None and not existing.done():
                    if existing.cancelling():
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "A previous stop request did not complete: the "
                                "metrics broadcast task was asked to stop and "
                                "is still running, so it may still be pushing "
                                "to WebSocket clients. Retry POST "
                                "/api/v1/monitoring/stop before starting "
                                "monitoring again."
                            ),
                        )

                # Update config if provided
                if request.config:
                    for key, value in request.config.items():
                        if hasattr(self.dashboard.config, key):
                            setattr(self.dashboard.config, key, value)

                # Start monitoring
                self.dashboard.start_monitoring(request.run_id)

                # Start WebSocket broadcasting unless it is already running.
                #
                # ``done()`` matters as much as ``is None``: a broadcast task
                # that raised, or whose loop condition went false, leaves a
                # truthy-but-dead handle, and only a SUCCESSFUL stop ever
                # clears it. Under the old truthiness test that handle blocked
                # task creation permanently, so every later start reported
                # ``started`` with nothing broadcasting at all.
                if existing is None or existing.done():
                    if existing is not None and not existing.cancelled():
                        previous_error = existing.exception()
                        if previous_error is not None:
                            # TYPE AND ORIGIN FRAMES, NEVER THE EXCEPTION
                            # ITSELF. ``_broadcast_metrics`` reaches the task
                            # manager and the dashboard's backing store, so
                            # what surfaces here can be a driver or transport
                            # error whose text carries a DSN or a token.
                            #
                            # A mask IS available to this tree --
                            # ``kailash.utils.url_credentials.mask_error_text``
                            # is plain core, already on this import path -- and
                            # it is deliberately NOT used. Measured, it masks
                            # TWO carriers and nothing else: URL userinfo (a
                            # postgres:// or redis:// DSN) and sensitive QUERY
                            # PARAMETERS (`?api_key=`, `?token=`, `?password=`).
                            # A credential that arrives in neither carrier
                            # passes through intact -- a BARE OpenAI key, a bare
                            # JWT, a Slack token, a 32-char Mistral key, an
                            # `Authorization: Basic` header.
                            # So masking here would be a porous filter over
                            # unbounded input, whereas the type plus the frame
                            # list are BOUNDED and structurally inert (both go
                            # through _safe_identifier) and are the whole
                            # diagnostic an operator needs to find the task.
                            # NOT payload-free: a caller-chosen class name
                            # survives, bounded and de-fanged, by design.
                            self.logger.warning(
                                "Previous metrics broadcast task ended with an "
                                "error; starting a replacement: %s at %s",
                                safe_type_name(previous_error),
                                safe_exception_frames(previous_error, limit=3),
                            )
                    self._broadcast_task = asyncio.create_task(
                        self._broadcast_metrics()
                    )

                return {"status": "started", "run_id": request.run_id}
            except HTTPException:
                # Already carries the precise reason; the handler below would
                # replace it with str(exc) and downgrade a 409 to a 500.
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="start monitoring"
                    ),
                ) from e

        @self.app.post("/api/v1/monitoring/stop")
        async def stop_monitoring():
            """Stop real-time monitoring."""
            try:
                self.dashboard.stop_monitoring()

                # Stop WebSocket broadcasting.
                #
                # ``cancel()`` only REQUESTS cancellation -- it returns without
                # establishing that the task stopped. The previous form
                # discarded that, nulled the handle, and returned
                # ``{"status": "stopped"}`` regardless, so a caller proceeded
                # on a broadcast task that could still be pushing frames. A
                # status field is a stronger claim than a log line: an
                # orchestrator acts on it.
                #
                # Nulling the handle was the worse half. ``stop_monitoring()``
                # above already clears ``dashboard._monitoring``, which is
                # this task's own ``while`` condition (see
                # ``_broadcast_metrics``), so once the handle is dropped the
                # task is both unreachable and unobservable: a retry has
                # nothing to act on, and ``start_monitoring``'s
                # ``if not self._broadcast_task`` would spawn a SECOND
                # broadcast task alongside a wedged first.
                if self._broadcast_task:
                    task = self._broadcast_task
                    task.cancel()
                    # ``asyncio.wait`` reports completion without re-raising
                    # the CancelledError the task ends with, so this observes
                    # the outcome without swallowing a cancellation aimed at
                    # THIS handler (which ``await task`` inside a try/except
                    # CancelledError would).
                    await asyncio.wait({task}, timeout=_BROADCAST_STOP_TIMEOUT_S)
                    if not task.done():
                        # Retain the handle: it is the only thing that can
                        # observe or retry this task.
                        self.logger.warning(
                            "Broadcast task did not stop within %ss; retaining "
                            "handle so a retry can act on it",
                            _BROADCAST_STOP_TIMEOUT_S,
                        )
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "Monitoring stopped, but the metrics broadcast "
                                f"task did not stop within "
                                f"{_BROADCAST_STOP_TIMEOUT_S}s and may still be "
                                "pushing to WebSocket clients. Retry the stop "
                                "request."
                            ),
                        )
                    self._broadcast_task = None

                return {"status": "stopped"}
            except HTTPException:
                # Already carries the precise reason; re-wrapping below would
                # replace it with str(exc) and lose the detail.
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="stop monitoring"
                    ),
                ) from e

        @self.app.get("/api/v1/monitoring/status")
        async def get_monitoring_status():
            """Get current monitoring status."""
            return {
                "monitoring": self.dashboard._monitoring,
                "run_id": self.dashboard._current_run_id,
                "metrics_count": len(self.dashboard._metrics_history),
                "websocket_connections": len(self._websocket_connections),
            }

        @self.app.get(
            "/api/v1/metrics/current", response_model=Optional[MetricsResponse]
        )
        async def get_current_metrics():
            """Get current live metrics."""
            try:
                metrics = self.dashboard.get_current_metrics()
                if not metrics:
                    return None

                return MetricsResponse(
                    timestamp=metrics.timestamp,
                    active_tasks=metrics.active_tasks,
                    completed_tasks=metrics.completed_tasks,
                    failed_tasks=metrics.failed_tasks,
                    total_cpu_usage=metrics.total_cpu_usage,
                    total_memory_usage=metrics.total_memory_usage,
                    throughput=metrics.throughput,
                    avg_task_duration=metrics.avg_task_duration,
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="get current metrics"
                    ),
                ) from e

        @self.app.get("/api/v1/metrics/history", response_model=list[MetricsResponse])
        async def get_metrics_history(minutes: int = 30):
            """Get metrics history for specified time period."""
            try:
                history = self.dashboard.get_metrics_history(minutes=minutes)

                return [
                    MetricsResponse(
                        timestamp=m.timestamp,
                        active_tasks=m.active_tasks,
                        completed_tasks=m.completed_tasks,
                        failed_tasks=m.failed_tasks,
                        total_cpu_usage=m.total_cpu_usage,
                        total_memory_usage=m.total_memory_usage,
                        throughput=m.throughput,
                        avg_task_duration=m.avg_task_duration,
                    )
                    for m in history
                ]
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="get metrics history"
                    ),
                ) from e

        @self.app.post("/api/v1/reports/generate")
        async def generate_report(request: ReportRequest, background_tasks: Any):
            """Generate performance report."""
            try:
                # Validate format
                try:
                    report_format = ReportFormat(request.format.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid format. Supported: {[f.value for f in ReportFormat]}",
                    )

                # Generate report in background
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = (
                    f"report_{request.run_id[:8]}_{timestamp}.{report_format.value}"
                )
                output_path = Path.cwd() / "outputs" / "reports" / filename

                background_tasks.add_task(
                    self._generate_report_background,
                    request.run_id,
                    output_path,
                    report_format,
                    request.compare_runs,
                )

                return {
                    "status": "generating",
                    "filename": filename,
                    "download_url": f"/api/v1/reports/download/{filename}",
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="generate report"
                    ),
                ) from e

        @self.app.get("/api/v1/reports/download/{filename}")
        async def download_report(filename: str):
            """Download generated report file."""
            try:
                file_path = Path.cwd() / "outputs" / "reports" / filename
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail="Report file not found")

                return FileResponse(
                    path=file_path,
                    filename=filename,
                    media_type="application/octet-stream",
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="download report"
                    ),
                ) from e

        @self.app.get("/api/v1/dashboard/live")
        async def get_live_dashboard():
            """Generate live dashboard HTML."""
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"dashboard_{timestamp}.html"
                output_path = Path.cwd() / "outputs" / "dashboards" / filename

                self.dashboard.generate_live_report(output_path, include_charts=True)

                return FileResponse(
                    path=output_path, filename=filename, media_type="text/html"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=safe_http_detail(
                        e, logger=self.logger, context="generate live dashboard"
                    ),
                ) from e

        @self.app.websocket("/api/v1/metrics/stream")
        async def websocket_metrics_stream(websocket: WebSocket):
            """WebSocket endpoint for real-time metrics streaming.

            The ``WebSocket`` annotation is load-bearing, not decoration.
            FastAPI resolves a websocket endpoint's parameters the same way it
            resolves a route's, and binds the socket ONLY to a parameter
            annotated with ``WebSocket``. Under the previous ``websocket: Any``
            the socket was never bound and ``websocket`` became a required
            QUERY PARAMETER, so every handshake failed validation and closed --
            measured on the route's own dependant::

                query_params    : ['websocket']   <- required query param
                websocket_param : None            <- socket never injected

            This route was therefore refusing every client, credentialed or
            not. Identical to the ``EnterpriseWorkflowServer`` ``/ws`` defect
            found in #2100, and it is what the credentialed control row in
            ``tests/regression/test_issue_2112_dashboard_api_auth.py`` exists
            to catch: without it, "anonymous handshake refused" reads green
            against a route that refuses everyone.
            """
            await websocket.accept()
            self._websocket_connections.append(websocket)

            try:
                while True:
                    # Keep connection alive
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self._websocket_connections.remove(websocket)
                self.logger.info("WebSocket client disconnected")
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}")
                if websocket in self._websocket_connections:
                    self._websocket_connections.remove(websocket)

        @self.app.websocket("/api/v1/metrics/ws")
        async def websocket_metrics_push(websocket: WebSocket):
            """WebSocket endpoint that pushes metrics at the dashboard update interval.

            Unlike ``/api/v1/metrics/stream`` which waits for client messages,
            this endpoint actively pushes the latest metrics snapshot to the
            client at the configured ``update_interval``.  This is the
            endpoint consumed by the live dashboard HTML page.

            Carried the same ``websocket: Any`` binding defect as
            ``/api/v1/metrics/stream`` above -- see that docstring. The live
            dashboard HTML page consumes THIS route, so the page's metrics
            never updated.
            """
            await websocket.accept()
            self._websocket_connections.append(websocket)

            try:
                while True:
                    current_metrics = self.dashboard.get_current_metrics()
                    if current_metrics:
                        payload = {
                            "type": "metrics",
                            "timestamp": current_metrics.timestamp.isoformat(),
                            "active_tasks": current_metrics.active_tasks,
                            "completed_tasks": current_metrics.completed_tasks,
                            "failed_tasks": current_metrics.failed_tasks,
                            "total_cpu_usage": current_metrics.total_cpu_usage,
                            "total_memory_usage": current_metrics.total_memory_usage,
                            "throughput": current_metrics.throughput,
                            "avg_task_duration": current_metrics.avg_task_duration,
                        }
                        await websocket.send_json(payload)

                    await asyncio.sleep(self.dashboard.config.update_interval)
            except WebSocketDisconnect:
                self.logger.info("WebSocket /ws client disconnected")
            except Exception as e:
                self.logger.error(f"WebSocket /ws error: {e}")
            finally:
                if websocket in self._websocket_connections:
                    self._websocket_connections.remove(websocket)

    async def _generate_report_background(
        self,
        run_id: str,
        output_path: Path,
        report_format: ReportFormat,
        compare_runs: list[str] | None = None,
    ):
        """Generate report in background task."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            self.reporter.generate_report(
                run_id=run_id,
                output_path=output_path,
                format=report_format,
                compare_runs=compare_runs,
            )

            self.logger.info(f"Generated background report: {output_path}")
        except Exception as e:
            self.logger.error(f"Background report generation failed: {e}")

    async def _broadcast_metrics(self):
        """Broadcast live metrics to WebSocket connections."""
        while self.dashboard._monitoring:
            try:
                if self._websocket_connections:
                    current_metrics = self.dashboard.get_current_metrics()
                    if current_metrics:
                        metrics_data = {
                            "timestamp": current_metrics.timestamp.isoformat(),
                            "active_tasks": current_metrics.active_tasks,
                            "completed_tasks": current_metrics.completed_tasks,
                            "failed_tasks": current_metrics.failed_tasks,
                            "total_cpu_usage": current_metrics.total_cpu_usage,
                            "total_memory_usage": current_metrics.total_memory_usage,
                            "throughput": current_metrics.throughput,
                            "avg_task_duration": current_metrics.avg_task_duration,
                        }

                        # Send to all connected clients
                        disconnected = []
                        for websocket in self._websocket_connections:
                            try:
                                await websocket.send_text(json.dumps(metrics_data))
                            except Exception as e:
                                self.logger.warning(
                                    f"Failed to send to WebSocket client: {e}"
                                )
                                disconnected.append(websocket)

                        # Remove disconnected clients
                        for ws in disconnected:
                            if ws in self._websocket_connections:
                                self._websocket_connections.remove(ws)

                await asyncio.sleep(self.dashboard.config.update_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Metrics broadcast error: {e}")
                await asyncio.sleep(1.0)

    def start_server(self, host: str = "127.0.0.1", port: int = 8000, **kwargs):
        """Start the API server.

        Args:
            host: Host to bind to
            port: Port to bind to
            **kwargs: Additional uvicorn server options
        """
        try:
            import uvicorn

            self.logger.info(f"Starting dashboard API server on {host}:{port}")
            uvicorn.run(self.app, host=host, port=port, **kwargs)
        except ImportError:
            raise ImportError(
                "uvicorn is required to run the API server. "
                "Install with: pip install uvicorn"
            )


class SimpleDashboardAPI:
    """Simplified API interface for dashboard functionality without FastAPI.

    This class provides dashboard API functionality using standard Python
    libraries for environments where FastAPI is not available or desired.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        dashboard_config: DashboardConfig | None = None,
    ):
        """Initialize simple API interface.

        Args:
            task_manager: TaskManager instance for data access
            dashboard_config: Configuration for dashboard components
        """
        self.task_manager = task_manager
        self.dashboard_config = dashboard_config or DashboardConfig()
        self.dashboard = RealTimeDashboard(task_manager, self.dashboard_config)
        self.reporter = WorkflowPerformanceReporter(task_manager)
        self.logger = logger

    def get_runs(self, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """Get list of workflow runs."""
        all_runs = self.task_manager.list_runs()
        runs = all_runs[offset : offset + limit]

        result = []
        for run in runs:
            tasks = self.task_manager.get_run_tasks(run.run_id)
            completed_count = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
            failed_count = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

            result.append(
                {
                    "run_id": run.run_id,
                    "workflow_name": run.workflow_name,
                    "status": run.status,
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "total_tasks": len(tasks),
                    "completed_tasks": completed_count,
                    "failed_tasks": failed_count,
                }
            )

        return result

    def get_run_details(self, run_id: str) -> dict[str, Any] | None:
        """Get details for a specific run."""
        run = self.task_manager.get_run(run_id)
        if not run:
            return None

        tasks = self.task_manager.get_run_tasks(run_id)
        completed_count = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed_count = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

        return {
            "run_id": run.run_id,
            "workflow_name": run.workflow_name,
            "status": run.status,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "total_tasks": len(tasks),
            "completed_tasks": completed_count,
            "failed_tasks": failed_count,
            "tasks": [
                {
                    "node_id": task.node_id,
                    "node_type": task.node_type,
                    "status": task.status,
                    "started_at": task.started_at,
                    "ended_at": task.ended_at,
                    "duration": task.metrics.duration if task.metrics else None,
                    "cpu_usage": task.metrics.cpu_usage if task.metrics else None,
                    "memory_usage_mb": (
                        task.metrics.memory_usage_mb if task.metrics else None
                    ),
                    "error_message": task.error,
                }
                for task in tasks
            ],
        }

    def start_monitoring(self, run_id: str | None = None) -> dict[str, Any]:
        """Start real-time monitoring."""
        self.dashboard.start_monitoring(run_id)
        return {"status": "started", "run_id": run_id}

    def stop_monitoring(self) -> dict[str, Any]:
        """Stop real-time monitoring."""
        self.dashboard.stop_monitoring()
        return {"status": "stopped"}

    def get_current_metrics(self) -> dict[str, Any] | None:
        """Get current live metrics."""
        metrics = self.dashboard.get_current_metrics()
        if not metrics:
            return None

        return {
            "timestamp": metrics.timestamp.isoformat(),
            "active_tasks": metrics.active_tasks,
            "completed_tasks": metrics.completed_tasks,
            "failed_tasks": metrics.failed_tasks,
            "total_cpu_usage": metrics.total_cpu_usage,
            "total_memory_usage": metrics.total_memory_usage,
            "throughput": metrics.throughput,
            "avg_task_duration": metrics.avg_task_duration,
        }

    def get_metrics_history(self, minutes: int = 30) -> list[dict[str, Any]]:
        """Get metrics history."""
        history = self.dashboard.get_metrics_history(minutes=minutes)

        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "active_tasks": m.active_tasks,
                "completed_tasks": m.completed_tasks,
                "failed_tasks": m.failed_tasks,
                "total_cpu_usage": m.total_cpu_usage,
                "total_memory_usage": m.total_memory_usage,
                "throughput": m.throughput,
                "avg_task_duration": m.avg_task_duration,
            }
            for m in history
        ]

    def generate_report(
        self,
        run_id: str,
        format: str = "html",
        output_path: str | Path | None = None,
        compare_runs: list[str] | None = None,
    ) -> Path:
        """Generate performance report."""
        try:
            report_format = ReportFormat(format.lower())
        except ValueError:
            raise ValueError(
                f"Invalid format. Supported: {[f.value for f in ReportFormat]}"
            )

        return self.reporter.generate_report(
            run_id=run_id,
            output_path=output_path,
            format=report_format,
            compare_runs=compare_runs,
        )

    def generate_dashboard(self, output_path: str | Path | None = None) -> Path:
        """Generate live dashboard HTML."""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path.cwd() / "outputs" / f"dashboard_{timestamp}.html"

        return self.dashboard.generate_live_report(output_path, include_charts=True)

    def export_metrics_json(self, output_path: str | Path | None = None) -> Path:
        """Export current metrics as JSON."""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path.cwd() / "outputs" / f"metrics_{timestamp}.json"

        from kailash.visualization.dashboard import DashboardExporter

        exporter = DashboardExporter(self.dashboard)
        return exporter.export_metrics_json(output_path)
