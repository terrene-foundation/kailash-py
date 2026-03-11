"""
HTTP /metrics endpoint for Prometheus scraping.

Provides FastAPI endpoint for exposing Prometheus metrics.
"""

import logging

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST

from ..builtin.metrics_hook import MetricsHook

logger = logging.getLogger(__name__)


class MetricsEndpoint:
    """
    HTTP endpoint for Prometheus metrics scraping.

    Provides a FastAPI app with /metrics endpoint that serves
    Prometheus-compatible metrics in text exposition format.

    Example:
        >>> hook = MetricsHook()
        >>> endpoint = MetricsEndpoint(hook, port=9090)
        >>> endpoint.start()  # Blocking call - starts HTTP server
    """

    def __init__(self, metrics_hook: MetricsHook, port: int = 9090):
        """
        Initialize metrics endpoint.

        Args:
            metrics_hook: MetricsHook instance to expose
            port: HTTP port for endpoint (default: 9090)
        """
        self.metrics_hook = metrics_hook
        self.port = port
        self.app = FastAPI(title="Kaizen Metrics", version="1.0.0")

        # Register /metrics endpoint
        @self.app.get("/metrics")
        async def metrics():
            """
            Prometheus metrics endpoint.

            Returns:
                Metrics in Prometheus text exposition format

            Example:
                $ curl http://localhost:9090/metrics
                # HELP kaizen_hook_events_total Total hook events by type and agent
                # TYPE kaizen_hook_events_total counter
                kaizen_hook_events_total{agent_id="agent1",event_type="pre_tool_use"} 5.0
            """
            try:
                data = self.metrics_hook.export_prometheus()
                return Response(content=data, media_type=CONTENT_TYPE_LATEST)
            except Exception as e:
                logger.error(f"Error exporting metrics: {e}")
                # SECURITY FIX #6: Don't leak error details to clients
                return Response(content="Internal server error", status_code=500)

        # Health check endpoint
        @self.app.get("/health")
        async def health():
            """Health check endpoint"""
            return {"status": "healthy", "metrics": "available"}

    def start(self):
        """
        Start HTTP server (blocking).

        This is a blocking call that runs the FastAPI server using uvicorn.

        Example:
            >>> endpoint = MetricsEndpoint(metrics_hook, port=9090)
            >>> endpoint.start()  # Runs forever
        """
        import uvicorn

        uvicorn.run(self.app, host="0.0.0.0", port=self.port)

    async def start_async(self):
        """
        Start HTTP server asynchronously.

        This is an async version that can be used in async contexts.

        Example:
            >>> async with anyio.create_task_group() as tg:
            ...     tg.start_soon(endpoint.start_async)
        """
        import uvicorn

        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port)
        server = uvicorn.Server(config)
        await server.serve()
