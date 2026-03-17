"""Tests for the WebSocket-powered live dashboard.

Validates HTML generation, theme support, and the /dashboard endpoint
on WorkflowServer.
"""

import pytest
from fastapi.testclient import TestClient

from src.kailash.servers import WorkflowServer
from src.kailash.visualization.live_dashboard import LiveDashboard


class TestLiveDashboardRender:
    """Tests for LiveDashboard.render()."""

    def test_render_returns_html(self):
        """render() produces valid HTML with expected structure."""
        dash = LiveDashboard(title="Test Dashboard")
        html = dash.render()

        assert "<!DOCTYPE html>" in html
        assert "<title>Test Dashboard</title>" in html
        assert "WebSocket" in html  # JS uses WebSocket
        assert "active_tasks" in html

    def test_explicit_ws_url(self):
        """Explicit ws_url is embedded in the JS."""
        dash = LiveDashboard(ws_url="ws://example.com/ws")
        html = dash.render()
        assert "ws://example.com/ws" in html

    def test_auto_detect_ws_url(self):
        """Without explicit ws_url, JS auto-detects from window.location."""
        dash = LiveDashboard()
        html = dash.render()
        assert "window.location.host" in html

    def test_dark_theme(self):
        """Dark theme applies dark background colours."""
        dash = LiveDashboard(theme="dark")
        html = dash.render()
        assert "#121212" in html  # dark bg


class TestLiveDashboardWrite:
    """Tests for LiveDashboard.write()."""

    def test_write_creates_file(self, tmp_path):
        """write() creates the HTML file at the given path."""
        out = tmp_path / "sub" / "dashboard.html"
        dash = LiveDashboard(title="Write Test")
        result = dash.write(out)

        assert result.exists()
        content = result.read_text()
        assert "Write Test" in content


class TestDashboardEndpoint:
    """Tests for the /dashboard endpoint on WorkflowServer."""

    def test_dashboard_returns_html(self):
        """GET /dashboard returns 200 with HTML content."""
        server = WorkflowServer(title="Dash Server")
        client = TestClient(server.app)

        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "WebSocket" in resp.text
