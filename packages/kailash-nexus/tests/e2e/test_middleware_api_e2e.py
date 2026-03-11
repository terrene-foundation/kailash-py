"""E2E tests for Nexus middleware API (TODO-300F).

End-to-end tests demonstrating complete middleware stacks with workflow
execution, environment switching, and preset integration.
Tier 3 tests - NO MOCKING. Real everything.
"""

import os

import pytest
from fastapi import APIRouter
from nexus import Nexus
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.testclient import TestClient

from kailash.workflow.builder import WorkflowBuilder

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_nexus_env(monkeypatch):
    """Ensure NEXUS_ENV is reset between tests."""
    monkeypatch.delenv("NEXUS_ENV", raising=False)


def _make_client(app: Nexus) -> TestClient:
    """Create a TestClient from a Nexus instance."""
    return TestClient(app._gateway.app)


# =============================================================================
# Tests: Complete Middleware Stack
# =============================================================================


class TestCompleteMiddlewareStack:
    """E2E tests for complete middleware stack processing."""

    def test_cors_plus_custom_middleware(self):
        """CORS + custom middleware both execute on requests."""
        execution_log = []

        class TimingMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                execution_log.append("timing-start")
                response = await call_next(request)
                execution_log.append("timing-end")
                return response

        app = Nexus(
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )
        app.add_middleware(TimingMiddleware)
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert "timing-start" in execution_log
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )

    def test_gzip_plus_cors_plus_router(self):
        """GZip + CORS + router endpoint all work together."""
        router = APIRouter()

        @router.get("/large-data")
        def large_data():
            return {"data": "x" * 2000}  # Large enough for gzip

        app = Nexus(
            cors_origins=["*"],
            enable_durability=False,
        )
        app.add_middleware(GZipMiddleware, minimum_size=500)
        app.include_router(router, prefix="/api")
        client = _make_client(app)

        response = client.get(
            "/api/large-data",
            headers={
                "Origin": "http://example.com",
                "Accept-Encoding": "gzip",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


# =============================================================================
# Tests: Workflow Execution with Middleware
# =============================================================================


class TestWorkflowExecutionWithMiddleware:
    """E2E tests for middleware + workflow execution."""

    def test_cors_with_workflow_execution(self):
        """CORS headers present on workflow execution endpoint."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "compute", {"code": "result = {'answer': 42}"}
        )
        app.register("test_workflow", workflow.build())
        client = _make_client(app)

        # Preflight for POST
        preflight = client.options(
            "/workflows/test_workflow/execute",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert preflight.status_code == 200

        # Actual POST
        response = client.post(
            "/workflows/test_workflow/execute",
            json={},
            headers={
                "Origin": "http://localhost:3000",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )

    def test_middleware_processes_workflow_request(self):
        """Custom middleware runs on workflow execution requests."""
        request_paths = []

        class PathLoggerMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request_paths.append(request.url.path)
                return await call_next(request)

        app = Nexus(enable_durability=False)
        app.add_middleware(PathLoggerMiddleware)

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "result = {'ok': True}"})
        app.register("my_workflow", workflow.build())
        client = _make_client(app)

        client.post("/workflows/my_workflow/execute", json={})

        assert "/workflows/my_workflow/execute" in request_paths


# =============================================================================
# Tests: Environment Switching
# =============================================================================


class TestEnvironmentSwitching:
    """E2E tests for environment-based configuration."""

    def test_development_allows_all_origins(self, monkeypatch):
        """Development environment allows all origins by default."""
        monkeypatch.setenv("NEXUS_ENV", "development")
        app = Nexus(enable_durability=False)
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://any-origin.example.com"},
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"

    def test_production_explicit_origins_only(self, monkeypatch):
        """Production requires explicit origins."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(
            cors_origins=["https://prod.example.com"],
            enable_auth=False,
            enable_durability=False,
        )
        client = _make_client(app)

        # Allowed origin
        allowed = client.get(
            "/health",
            headers={"Origin": "https://prod.example.com"},
        )
        assert (
            allowed.headers["access-control-allow-origin"] == "https://prod.example.com"
        )

        # Blocked origin
        blocked = client.get(
            "/health",
            headers={"Origin": "https://evil.com"},
        )
        assert "access-control-allow-origin" not in blocked.headers

    def test_production_rejects_wildcard(self, monkeypatch):
        """Production raises ValueError for wildcard origins."""
        monkeypatch.setenv("NEXUS_ENV", "production")

        with pytest.raises(ValueError, match="not allowed in production"):
            Nexus(
                cors_origins=["*"],
                enable_auth=False,
                enable_durability=False,
            )


# =============================================================================
# Tests: Preset E2E
# =============================================================================


class TestPresetE2E:
    """E2E tests for preset integration."""

    def test_lightweight_preset_full_flow(self):
        """Lightweight preset: CORS works on real requests."""
        app = Nexus(
            preset="lightweight",
            cors_origins=["http://localhost:5173"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )

        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )

    def test_preset_with_workflow_and_router(self):
        """Preset + workflow + router all work together."""
        router = APIRouter()

        @router.get("/status")
        def status():
            return {"status": "ok"}

        app = Nexus(
            preset="lightweight",
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )
        app.include_router(router, prefix="/api")

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "test", {"code": "result = {'computed': True}"}
        )
        app.register("compute", workflow.build())
        client = _make_client(app)

        # Router endpoint works
        status_resp = client.get("/api/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "ok"

        # Workflow endpoint works
        workflow_resp = client.post("/workflows/compute/execute", json={})
        assert workflow_resp.status_code == 200

    def test_describe_preset_after_setup(self):
        """describe_preset() returns correct info after full setup."""
        app = Nexus(
            preset="lightweight",
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )

        info = app.describe_preset()

        assert info["preset"] == "lightweight"
        assert "CORS" in info["description"]
        assert len(info["middleware"]) > 0
