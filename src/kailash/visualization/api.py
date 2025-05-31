"""API endpoints for real-time dashboard data access.

This module provides REST API endpoints for accessing real-time workflow
performance data, metrics, and dashboard components for web-based interfaces.

Design Purpose:
- Provide RESTful API access to live performance metrics
- Enable real-time dashboard updates via HTTP endpoints
- Support WebSocket connections for streaming data
- Integrate with web dashboard frameworks and monitoring tools

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

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from fastapi import (
        BackgroundTasks,
        FastAPI,
        HTTPException,
        WebSocket,
        WebSocketDisconnect,
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from pydantic import BaseModel

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskStatus
from kailash.visualization.dashboard import DashboardConfig, RealTimeDashboard
from kailash.visualization.reports import ReportFormat, WorkflowPerformanceReporter

logger = logging.getLogger(__name__)


# Pydantic models for API requests/responses
if FASTAPI_AVAILABLE:

    class RunRequest(BaseModel):
        """Request model for starting monitoring."""

        run_id: Optional[str] = None
        config: Optional[Dict[str, Any]] = None

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
        started_at: Optional[datetime]
        ended_at: Optional[datetime]
        duration: Optional[float]
        cpu_usage: Optional[float]
        memory_usage_mb: Optional[float]
        error_message: Optional[str]

    class RunResponse(BaseModel):
        """Response model for run information."""

        run_id: str
        workflow_name: str
        status: str
        started_at: Optional[datetime]
        ended_at: Optional[datetime]
        total_tasks: int
        completed_tasks: int
        failed_tasks: int

    class ReportRequest(BaseModel):
        """Request model for generating reports."""

        run_id: str
        format: str = "html"
        include_charts: bool = True
        compare_runs: Optional[List[str]] = None
        detail_level: str = "detailed"


class DashboardAPIServer:
    """FastAPI server for dashboard API endpoints.

    This class provides a complete REST API server for accessing real-time
    workflow performance data and dashboard components.

    Usage:
        api_server = DashboardAPIServer(task_manager)
        api_server.start_server(host="0.0.0.0", port=8000)
    """

    def __init__(
        self,
        task_manager: TaskManager,
        dashboard_config: Optional[DashboardConfig] = None,
    ):
        """Initialize API server.

        Args:
            task_manager: TaskManager instance for data access
            dashboard_config: Configuration for dashboard components
        """
        if not FASTAPI_AVAILABLE:
            raise ImportError(
                "FastAPI is required for API server functionality. "
                "Install with: pip install fastapi uvicorn"
            )

        self.task_manager = task_manager
        self.dashboard_config = dashboard_config or DashboardConfig()

        # Initialize dashboard and reporter
        self.dashboard = RealTimeDashboard(task_manager, self.dashboard_config)
        self.reporter = WorkflowPerformanceReporter(task_manager)

        # WebSocket connections for real-time updates
        self._websocket_connections: List[WebSocket] = []
        self._broadcast_task: Optional[asyncio.Task] = None

        # Create FastAPI app
        self.app = FastAPI(
            title="Kailash Dashboard API",
            description="Real-time workflow performance monitoring API",
            version="1.0.0",
        )

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
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

        @self.app.get("/api/v1/runs", response_model=List[RunResponse])
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
                self.logger.error(f"Failed to list runs: {e}")
                raise HTTPException(status_code=500, detail=str(e))

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
                self.logger.error(f"Failed to get run {run_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/v1/runs/{run_id}/tasks", response_model=List[TaskResponse])
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
                self.logger.error(f"Failed to get tasks for run {run_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/v1/monitoring/start")
        async def start_monitoring(request: RunRequest):
            """Start real-time monitoring for a run."""
            try:
                # Update config if provided
                if request.config:
                    for key, value in request.config.items():
                        if hasattr(self.dashboard.config, key):
                            setattr(self.dashboard.config, key, value)

                # Start monitoring
                self.dashboard.start_monitoring(request.run_id)

                # Start WebSocket broadcasting if not already running
                if not self._broadcast_task:
                    self._broadcast_task = asyncio.create_task(
                        self._broadcast_metrics()
                    )

                return {"status": "started", "run_id": request.run_id}
            except Exception as e:
                self.logger.error(f"Failed to start monitoring: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/v1/monitoring/stop")
        async def stop_monitoring():
            """Stop real-time monitoring."""
            try:
                self.dashboard.stop_monitoring()

                # Stop WebSocket broadcasting
                if self._broadcast_task:
                    self._broadcast_task.cancel()
                    self._broadcast_task = None

                return {"status": "stopped"}
            except Exception as e:
                self.logger.error(f"Failed to stop monitoring: {e}")
                raise HTTPException(status_code=500, detail=str(e))

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
                self.logger.error(f"Failed to get current metrics: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/v1/metrics/history", response_model=List[MetricsResponse])
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
                self.logger.error(f"Failed to get metrics history: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/v1/reports/generate")
        async def generate_report(
            request: ReportRequest, background_tasks: BackgroundTasks
        ):
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
                self.logger.error(f"Failed to generate report: {e}")
                raise HTTPException(status_code=500, detail=str(e))

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
                self.logger.error(f"Failed to download report {filename}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

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
                self.logger.error(f"Failed to generate live dashboard: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.websocket("/api/v1/metrics/stream")
        async def websocket_metrics_stream(websocket: WebSocket):
            """WebSocket endpoint for real-time metrics streaming."""
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

    async def _generate_report_background(
        self,
        run_id: str,
        output_path: Path,
        report_format: ReportFormat,
        compare_runs: Optional[List[str]] = None,
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

    def start_server(self, host: str = "0.0.0.0", port: int = 8000, **kwargs):
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
        dashboard_config: Optional[DashboardConfig] = None,
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

    def get_runs(self, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
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

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
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

    def start_monitoring(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Start real-time monitoring."""
        self.dashboard.start_monitoring(run_id)
        return {"status": "started", "run_id": run_id}

    def stop_monitoring(self) -> Dict[str, Any]:
        """Stop real-time monitoring."""
        self.dashboard.stop_monitoring()
        return {"status": "stopped"}

    def get_current_metrics(self) -> Optional[Dict[str, Any]]:
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

    def get_metrics_history(self, minutes: int = 30) -> List[Dict[str, Any]]:
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
        output_path: Optional[Union[str, Path]] = None,
        compare_runs: Optional[List[str]] = None,
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

    def generate_dashboard(
        self, output_path: Optional[Union[str, Path]] = None
    ) -> Path:
        """Generate live dashboard HTML."""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path.cwd() / "outputs" / f"dashboard_{timestamp}.html"

        return self.dashboard.generate_live_report(output_path, include_charts=True)

    def export_metrics_json(
        self, output_path: Optional[Union[str, Path]] = None
    ) -> Path:
        """Export current metrics as JSON."""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path.cwd() / "outputs" / f"metrics_{timestamp}.json"

        from kailash.visualization.dashboard import DashboardExporter

        exporter = DashboardExporter(self.dashboard)
        return exporter.export_metrics_json(output_path)
