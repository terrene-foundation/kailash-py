# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane web dashboard."""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from http.client import HTTPConnection
from pathlib import Path

import pytest
from click.testing import CliRunner

from kailash.trust.plane.cli import main
from kailash.trust.plane.dashboard import (
    create_dashboard_handler,
    load_or_create_token,
    serve_dashboard,
)
from kailash.trust.plane.holds import HoldManager
from kailash.trust.plane.project import TrustProject


def _run(coro):
    """Run an async coroutine synchronously."""
    import asyncio

    return asyncio.run(coro)


def _init_project(tmp_path: Path) -> tuple[TrustProject, str]:
    """Initialize a test project and return (project, trust_dir)."""
    trust_dir = str(tmp_path / "trust-plane")
    project = _run(
        TrustProject.create(
            trust_dir=trust_dir,
            project_name="Dashboard Test",
            author="TestUser",
        )
    )
    return project, trust_dir


def _wait_for_server(url: str, timeout: float = 5.0) -> None:
    """Poll the server until it responds or timeout is reached.

    Args:
        url: Full URL to probe (e.g. ``http://127.0.0.1:8080/``).
        timeout: Maximum seconds to wait before raising.

    Raises:
        TimeoutError: If the server does not respond within *timeout*.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            conn = HTTPConnection(
                url.split("//")[1].split("/")[0].split(":")[0],
                int(url.split(":")[-1].split("/")[0]),
                timeout=1,
            )
            conn.request("GET", "/")
            conn.getresponse()
            conn.close()
            return
        except (ConnectionRefusedError, OSError):
            time.sleep(0.05)
    raise TimeoutError(f"Server at {url} did not respond within {timeout}s")


def _start_test_server(
    trust_dir: str, port: int, auth_token: str | None = None
) -> tuple[threading.Thread, HTTPConnection]:
    """Start a dashboard server in a background thread and return (thread, connection).

    Args:
        trust_dir: Path to the trust-plane project directory.
        port: Port to bind on.
        auth_token: Optional bearer token for API authentication.
            ``None`` disables auth (default, backward-compatible).
    """
    import asyncio
    from http.server import HTTPServer

    project = asyncio.run(TrustProject.load(trust_dir))
    hold_manager = HoldManager(Path(trust_dir), store=project._tp_store)
    handler = create_dashboard_handler(project, hold_manager, auth_token=auth_token)

    server = HTTPServer(("127.0.0.1", port), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Wait for the server to be ready to accept connections
    _wait_for_server(f"http://127.0.0.1:{port}/", timeout=5.0)

    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    return thread, conn, server


class TestDashboardStartsAndResponds:
    """Dashboard starts and responds to requests."""

    def test_overview_page_responds(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/")
            resp = conn.getresponse()
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "TrustPlane" in body
            assert "Dashboard Test" in body
        finally:
            server.shutdown()
            conn.close()

    def test_decisions_page_responds(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/decisions")
            resp = conn.getresponse()
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "Decisions" in body
        finally:
            server.shutdown()
            conn.close()

    def test_milestones_page_responds(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/milestones")
            resp = conn.getresponse()
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "Milestones" in body
        finally:
            server.shutdown()
            conn.close()

    def test_holds_page_responds(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/holds")
            resp = conn.getresponse()
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "Holds" in body
        finally:
            server.shutdown()
            conn.close()

    def test_verify_page_responds(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/verify")
            resp = conn.getresponse()
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "Verification" in body
        finally:
            server.shutdown()
            conn.close()

    def test_404_for_unknown_route(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/nonexistent")
            resp = conn.getresponse()
            assert resp.status == 404
        finally:
            server.shutdown()
            conn.close()


class TestOverviewWithEmptyStore:
    """Overview page renders with empty store."""

    def test_overview_shows_zero_counts(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            # Empty store should show 0 for all counts
            assert "Dashboard Test" in body
            assert "TestUser" in body
            # Check for the stat values — 0 decisions, milestones, holds
            assert ">0<" in body  # at least one zero stat
        finally:
            server.shutdown()
            conn.close()

    def test_overview_shows_valid_badge(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            # Fresh project should have valid chain
            assert "VALID" in body
        finally:
            server.shutdown()
            conn.close()

    def test_empty_decisions_table(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/decisions")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            assert "No decisions recorded yet" in body
        finally:
            server.shutdown()
            conn.close()


class TestAPIEndpoints:
    """API endpoints return valid JSON with pagination envelope."""

    def test_api_decisions_returns_json(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions")
            resp = conn.getresponse()
            assert resp.status == 200
            assert "application/json" in resp.getheader("Content-Type")
            data = json.loads(resp.read().decode("utf-8"))
            assert isinstance(data, dict)
            assert isinstance(data["items"], list)
            assert len(data["items"]) == 0  # empty store
            assert data["total_count"] == 0
            assert data["has_more"] is False
        finally:
            server.shutdown()
            conn.close()

    def test_api_milestones_returns_json(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/milestones")
            resp = conn.getresponse()
            assert resp.status == 200
            assert "application/json" in resp.getheader("Content-Type")
            data = json.loads(resp.read().decode("utf-8"))
            assert isinstance(data, dict)
            assert isinstance(data["items"], list)
            assert data["has_more"] is False
        finally:
            server.shutdown()
            conn.close()

    def test_api_holds_returns_json(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/holds")
            resp = conn.getresponse()
            assert resp.status == 200
            assert "application/json" in resp.getheader("Content-Type")
            data = json.loads(resp.read().decode("utf-8"))
            assert isinstance(data, dict)
            assert isinstance(data["items"], list)
            assert data["has_more"] is False
        finally:
            server.shutdown()
            conn.close()

    def test_api_verify_returns_json(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/verify")
            resp = conn.getresponse()
            assert resp.status == 200
            assert "application/json" in resp.getheader("Content-Type")
            data = json.loads(resp.read().decode("utf-8"))
            assert isinstance(data, dict)
            assert "chain_valid" in data
        finally:
            server.shutdown()
            conn.close()

    def test_api_decisions_with_data(self, tmp_path):
        """API returns decisions when they exist."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project, trust_dir = _init_project(tmp_path)
        record = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="Test decision for API",
            rationale="Testing the dashboard API",
        )
        _run(project.record_decision(record))

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data["items"]) == 1
            assert data["items"][0]["decision"] == "Test decision for API"
            assert data["total_count"] == 1
            assert data["has_more"] is False
        finally:
            server.shutdown()
            conn.close()

    def test_api_decisions_type_filter(self, tmp_path):
        """API filters decisions by type."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project, trust_dir = _init_project(tmp_path)
        _run(
            project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.SCOPE,
                    decision="Scope decision",
                    rationale="Test",
                )
            )
        )
        _run(
            project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.DESIGN,
                    decision="Design decision",
                    rationale="Test",
                )
            )
        )

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?type=scope")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data["items"]) == 1
            assert data["items"][0]["decision"] == "Scope decision"
            assert data["total_count"] == 1
        finally:
            server.shutdown()
            conn.close()


class TestAPIPagination:
    """API endpoints enforce pagination limits (TODO-58)."""

    def test_default_pagination_limit_is_100(self, tmp_path):
        """Without explicit limit, API uses default limit of 100."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            # Empty store, but verify pagination metadata is present
            assert "items" in data
            assert "total_count" in data
            assert "has_more" in data
            assert "next_offset" in data
            assert data["has_more"] is False
            assert data["next_offset"] is None
        finally:
            server.shutdown()
            conn.close()

    def test_custom_limit_parameter(self, tmp_path):
        """API accepts a custom limit parameter."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project, trust_dir = _init_project(tmp_path)
        # Create 5 decisions
        for i in range(5):
            _run(
                project.record_decision(
                    DecisionRecord(
                        decision_type=DecisionType.SCOPE,
                        decision=f"Decision {i}",
                        rationale="Test",
                    )
                )
            )

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?limit=3")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data["items"]) == 3
            assert data["total_count"] == 5
            assert data["has_more"] is True
            assert data["next_offset"] == 3
        finally:
            server.shutdown()
            conn.close()

    def test_custom_offset_parameter(self, tmp_path):
        """API accepts a custom offset parameter."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project, trust_dir = _init_project(tmp_path)
        # Create 5 decisions
        for i in range(5):
            _run(
                project.record_decision(
                    DecisionRecord(
                        decision_type=DecisionType.SCOPE,
                        decision=f"Decision {i}",
                        rationale="Test",
                    )
                )
            )

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?limit=3&offset=3")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data["items"]) == 2  # only 2 left after offset 3
            assert data["total_count"] == 5
            assert data["has_more"] is False
            assert data["next_offset"] is None
        finally:
            server.shutdown()
            conn.close()

    def test_limit_exceeding_1000_returns_400(self, tmp_path):
        """Requesting limit > 1000 returns 400 error."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?limit=1001")
            resp = conn.getresponse()
            assert resp.status == 400
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
            assert "1000" in data["error"]
        finally:
            server.shutdown()
            conn.close()

    def test_limit_exactly_1000_is_allowed(self, tmp_path):
        """Requesting limit=1000 is allowed (boundary check)."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?limit=1000")
            resp = conn.getresponse()
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "items" in data
        finally:
            server.shutdown()
            conn.close()

    def test_negative_limit_returns_400(self, tmp_path):
        """Requesting a negative limit returns 400 error."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?limit=-1")
            resp = conn.getresponse()
            assert resp.status == 400
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
        finally:
            server.shutdown()
            conn.close()

    def test_zero_limit_returns_400(self, tmp_path):
        """Requesting limit=0 returns 400 error."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?limit=0")
            resp = conn.getresponse()
            assert resp.status == 400
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
        finally:
            server.shutdown()
            conn.close()

    def test_negative_offset_returns_400(self, tmp_path):
        """Requesting a negative offset returns 400 error."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?offset=-1")
            resp = conn.getresponse()
            assert resp.status == 400
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
        finally:
            server.shutdown()
            conn.close()

    def test_non_numeric_limit_returns_400(self, tmp_path):
        """Non-numeric limit returns 400 error."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?limit=abc")
            resp = conn.getresponse()
            assert resp.status == 400
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
        finally:
            server.shutdown()
            conn.close()

    def test_non_numeric_offset_returns_400(self, tmp_path):
        """Non-numeric offset returns 400 error."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions?offset=xyz")
            resp = conn.getresponse()
            assert resp.status == 400
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
        finally:
            server.shutdown()
            conn.close()

    def test_milestones_pagination(self, tmp_path):
        """Milestones endpoint also has pagination."""
        project, trust_dir = _init_project(tmp_path)
        for i in range(5):
            _run(project.record_milestone(f"v0.{i}", f"Milestone {i}", ""))

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/milestones?limit=2")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert len(data["items"]) == 2
            assert data["total_count"] == 5
            assert data["has_more"] is True
            assert data["next_offset"] == 2
        finally:
            server.shutdown()
            conn.close()

    def test_holds_pagination(self, tmp_path):
        """Holds endpoint also has pagination."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/holds?limit=50")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert "items" in data
            assert "total_count" in data
            assert "has_more" in data
            assert "next_offset" in data
        finally:
            server.shutdown()
            conn.close()

    def test_milestones_limit_exceeding_1000_returns_400(self, tmp_path):
        """Milestones endpoint also rejects limit > 1000."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/milestones?limit=2000")
            resp = conn.getresponse()
            assert resp.status == 400
        finally:
            server.shutdown()
            conn.close()

    def test_holds_limit_exceeding_1000_returns_400(self, tmp_path):
        """Holds endpoint also rejects limit > 1000."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/holds?limit=5000")
            resp = conn.getresponse()
            assert resp.status == 400
        finally:
            server.shutdown()
            conn.close()

    def test_pagination_metadata_structure(self, tmp_path):
        """Pagination response has correct metadata keys and types."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project, trust_dir = _init_project(tmp_path)
        _run(
            project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.SCOPE,
                    decision="Test",
                    rationale="Test",
                )
            )
        )

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/api/decisions")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            # Verify structure
            assert isinstance(data["items"], list)
            assert isinstance(data["total_count"], int)
            assert isinstance(data["has_more"], bool)
            # next_offset is int or None
            assert data["next_offset"] is None or isinstance(data["next_offset"], int)
        finally:
            server.shutdown()
            conn.close()

    def test_html_pagination_still_works(self, tmp_path):
        """HTML page pagination is unaffected by API pagination changes."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project, trust_dir = _init_project(tmp_path)
        # Create enough decisions to trigger HTML pagination (> 25)
        for i in range(30):
            _run(
                project.record_decision(
                    DecisionRecord(
                        decision_type=DecisionType.SCOPE,
                        decision=f"Decision {i}",
                        rationale="Test",
                    )
                )
            )

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            # HTML page should still paginate at 25 items per page
            conn.request("GET", "/decisions")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "text/html" in resp.getheader("Content-Type")
            # Should show pagination links
            assert "page=" in body
        finally:
            server.shutdown()
            conn.close()


class TestDashboardHTML:
    """Dashboard serves correct HTML."""

    def test_html_content_type(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/")
            resp = conn.getresponse()
            assert "text/html" in resp.getheader("Content-Type")
        finally:
            server.shutdown()
            conn.close()

    def test_html_has_nav_links(self, tmp_path):
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            assert 'href="/decisions"' in body
            assert 'href="/milestones"' in body
            assert 'href="/holds"' in body
            assert 'href="/verify"' in body
            assert 'href="/api/decisions"' in body
        finally:
            server.shutdown()
            conn.close()

    def test_decisions_page_with_data(self, tmp_path):
        """Decisions page renders records correctly."""
        from kailash.trust.plane.models import DecisionRecord, DecisionType

        project, trust_dir = _init_project(tmp_path)
        _run(
            project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.TECHNICAL,
                    decision="Use Python stdlib",
                    rationale="No external deps",
                )
            )
        )

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/decisions")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            assert "Use Python stdlib" in body
            assert "No external deps" in body
            assert "technical" in body
        finally:
            server.shutdown()
            conn.close()

    def test_milestones_page_with_data(self, tmp_path):
        """Milestones page renders records correctly."""
        project, trust_dir = _init_project(tmp_path)
        _run(project.record_milestone("v0.1", "Initial draft", ""))

        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/milestones")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            assert "v0.1" in body
            assert "Initial draft" in body
        finally:
            server.shutdown()
            conn.close()

    def test_verify_page_shows_valid(self, tmp_path):
        """Verify page shows VALID for fresh project."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port)
        try:
            conn.request("GET", "/verify")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            assert "VALID" in body
        finally:
            server.shutdown()
            conn.close()


class TestCLIDashboard:
    """CLI dashboard command exists and shows help."""

    def test_dashboard_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["dashboard", "--help"])
        assert result.exit_code == 0
        assert "trust status dashboard" in result.output.lower()
        assert "--port" in result.output
        assert "--open" in result.output
        assert "--no-auth" in result.output

    def test_dashboard_no_project(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "nothing")
        result = runner.invoke(main, ["--dir", trust_dir, "dashboard"])
        assert result.exit_code == 1
        assert "No project found" in result.output


class TestBearerTokenAuth:
    """Bearer token authentication for API endpoints (TODO-53)."""

    def test_api_returns_401_without_token(self, tmp_path):
        """API endpoints return 401 when auth is enabled and no token provided."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(
            trust_dir, port, auth_token="test-secret-token"
        )
        try:
            conn.request("GET", "/api/decisions")
            resp = conn.getresponse()
            assert resp.status == 401
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
            assert "Authentication required" in data["error"]
        finally:
            server.shutdown()
            conn.close()

    def test_api_returns_401_with_wrong_token(self, tmp_path):
        """API endpoints return 401 when token is incorrect."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(
            trust_dir, port, auth_token="test-secret-token"
        )
        try:
            conn.request(
                "GET",
                "/api/decisions",
                headers={"Authorization": "Bearer wrong-token"},
            )
            resp = conn.getresponse()
            assert resp.status == 401
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
            assert "Invalid bearer token" in data["error"]
        finally:
            server.shutdown()
            conn.close()

    def test_api_returns_401_with_bad_format(self, tmp_path):
        """API endpoints return 401 when Authorization header format is wrong."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(
            trust_dir, port, auth_token="test-secret-token"
        )
        try:
            conn.request(
                "GET",
                "/api/decisions",
                headers={"Authorization": "Basic dXNlcjpwYXNz"},
            )
            resp = conn.getresponse()
            assert resp.status == 401
            data = json.loads(resp.read().decode("utf-8"))
            assert "error" in data
            assert "Invalid Authorization header format" in data["error"]
        finally:
            server.shutdown()
            conn.close()

    def test_api_returns_200_with_correct_token(self, tmp_path):
        """API endpoints return 200 when correct bearer token is provided."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        token = "test-secret-token"
        thread, conn, server = _start_test_server(trust_dir, port, auth_token=token)
        try:
            conn.request(
                "GET",
                "/api/decisions",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = conn.getresponse()
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "items" in data
        finally:
            server.shutdown()
            conn.close()

    def test_html_pages_accessible_without_token(self, tmp_path):
        """HTML pages do not require authentication even when auth is enabled."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(
            trust_dir, port, auth_token="test-secret-token"
        )
        try:
            # Overview page should work without auth
            conn.request("GET", "/")
            resp = conn.getresponse()
            assert resp.status == 200
            resp.read()  # drain body

            # Decisions page should work without auth
            conn.request("GET", "/decisions")
            resp = conn.getresponse()
            assert resp.status == 200
            resp.read()

            # Milestones page should work without auth
            conn.request("GET", "/milestones")
            resp = conn.getresponse()
            assert resp.status == 200
            resp.read()

            # Holds page should work without auth
            conn.request("GET", "/holds")
            resp = conn.getresponse()
            assert resp.status == 200
            resp.read()

            # Verify page should work without auth
            conn.request("GET", "/verify")
            resp = conn.getresponse()
            assert resp.status == 200
        finally:
            server.shutdown()
            conn.close()

    def test_no_auth_mode_allows_api_without_token(self, tmp_path):
        """When auth_token is None (--no-auth), API works without token."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(trust_dir, port, auth_token=None)
        try:
            conn.request("GET", "/api/decisions")
            resp = conn.getresponse()
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "items" in data
        finally:
            server.shutdown()
            conn.close()

    def test_all_api_endpoints_require_auth(self, tmp_path):
        """All four API endpoints require authentication."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        thread, conn, server = _start_test_server(
            trust_dir, port, auth_token="test-secret-token"
        )
        try:
            for endpoint in [
                "/api/decisions",
                "/api/milestones",
                "/api/holds",
                "/api/verify",
            ]:
                conn.request("GET", endpoint)
                resp = conn.getresponse()
                assert resp.status == 401, f"{endpoint} should require auth"
                resp.read()  # drain body
        finally:
            server.shutdown()
            conn.close()

    def test_all_api_endpoints_work_with_token(self, tmp_path):
        """All four API endpoints accept a valid bearer token."""
        _, trust_dir = _init_project(tmp_path)
        port = _find_free_port()
        token = "test-secret-token"
        thread, conn, server = _start_test_server(trust_dir, port, auth_token=token)
        try:
            for endpoint in [
                "/api/decisions",
                "/api/milestones",
                "/api/holds",
                "/api/verify",
            ]:
                conn.request(
                    "GET",
                    endpoint,
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp = conn.getresponse()
                assert resp.status == 200, f"{endpoint} should succeed with token"
                resp.read()  # drain body
        finally:
            server.shutdown()
            conn.close()


class TestTokenManagement:
    """Token file management (load_or_create_token)."""

    def test_creates_token_file(self, tmp_path):
        """First call creates a new token file."""
        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        token = load_or_create_token(str(trust_dir))
        assert len(token) > 0
        token_path = trust_dir / ".dashboard-token"
        assert token_path.exists()
        assert token_path.read_text().strip() == token

    def test_returns_existing_token(self, tmp_path):
        """Second call returns the same token."""
        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        token1 = load_or_create_token(str(trust_dir))
        token2 = load_or_create_token(str(trust_dir))
        assert token1 == token2

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Unix file permission checks not applicable on Windows",
    )
    def test_token_file_permissions(self, tmp_path):
        """Token file has 0o600 permissions (owner-only)."""
        import os
        import stat

        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        load_or_create_token(str(trust_dir))
        token_path = trust_dir / ".dashboard-token"
        mode = os.stat(token_path).st_mode
        # Check owner read+write, no group/other
        assert mode & stat.S_IRUSR  # owner read
        assert mode & stat.S_IWUSR  # owner write
        assert not (mode & stat.S_IRGRP)  # no group read
        assert not (mode & stat.S_IWGRP)  # no group write
        assert not (mode & stat.S_IROTH)  # no other read
        assert not (mode & stat.S_IWOTH)  # no other write

    def test_token_is_url_safe(self, tmp_path):
        """Generated token contains only URL-safe characters."""
        import re

        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        token = load_or_create_token(str(trust_dir))
        # secrets.token_urlsafe uses base64url: [A-Za-z0-9_-]
        assert re.fullmatch(r"[A-Za-z0-9_-]+", token)

    def test_replaces_empty_token_file(self, tmp_path):
        """If token file exists but is empty, a new token is generated."""
        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        token_path = trust_dir / ".dashboard-token"
        token_path.write_text("")
        token = load_or_create_token(str(trust_dir))
        assert len(token) > 0
        assert token_path.read_text().strip() == token


def _find_free_port() -> int:
    """Find a free port on localhost."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
