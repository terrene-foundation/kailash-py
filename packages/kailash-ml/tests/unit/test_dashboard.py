# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the ML dashboard server.

Uses Starlette's TestClient with a real SQLite database via ConnectionManager.
All API endpoints and HTML serving are tested with real data.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from kailash.db.connection import ConnectionManager
from kailash_ml.dashboard.server import create_app
from kailash_ml.engines.experiment_tracker import ExperimentTracker
from kailash_ml.engines.model_registry import ModelRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    """Real SQLite ConnectionManager for tests."""
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def tracker(conn: ConnectionManager, tmp_path: Path) -> ExperimentTracker:
    """ExperimentTracker backed by real SQLite."""
    return ExperimentTracker(conn, artifact_root=str(tmp_path / "mlartifacts"))


@pytest.fixture
async def registry(conn: ConnectionManager) -> ModelRegistry:
    """ModelRegistry backed by real SQLite."""
    return ModelRegistry(conn)


@pytest.fixture
def client(tracker: ExperimentTracker, registry: ModelRegistry) -> TestClient:
    """Starlette TestClient wired to real engines."""
    app = create_app(tracker, registry)
    return TestClient(app)


@pytest.fixture
async def seeded_tracker(
    tracker: ExperimentTracker, tmp_path: Path
) -> ExperimentTracker:
    """Tracker with pre-seeded experiment, runs, params, and metrics."""
    # Create experiment with 2 runs
    run1 = await tracker.start_run("my-experiment", run_name="run-alpha")
    await tracker.log_params(run1.id, {"lr": "0.01", "epochs": "10"})
    await tracker.log_metric(run1.id, "loss", 0.9, step=0)
    await tracker.log_metric(run1.id, "loss", 0.5, step=1)
    await tracker.log_metric(run1.id, "loss", 0.2, step=2)
    await tracker.log_metric(run1.id, "accuracy", 0.75, step=0)
    await tracker.log_metric(run1.id, "accuracy", 0.90, step=1)

    # Log an artifact
    artifact_file = tmp_path / "model.pkl"
    artifact_file.write_bytes(b"fake-model-bytes")
    await tracker.log_artifact(run1.id, str(artifact_file))

    await tracker.end_run(run1.id, "COMPLETED")

    run2 = await tracker.start_run("my-experiment", run_name="run-beta")
    await tracker.log_params(run2.id, {"lr": "0.001", "epochs": "20"})
    await tracker.log_metric(run2.id, "loss", 0.8, step=0)
    await tracker.log_metric(run2.id, "loss", 0.3, step=1)
    await tracker.log_metric(run2.id, "accuracy", 0.85, step=0)
    await tracker.log_metric(run2.id, "accuracy", 0.95, step=1)
    await tracker.end_run(run2.id, "COMPLETED")

    # Store run IDs for test access
    tracker._test_run_ids = [run1.id, run2.id]  # type: ignore[attr-defined]

    return tracker


@pytest.fixture
def seeded_client(
    seeded_tracker: ExperimentTracker, registry: ModelRegistry
) -> TestClient:
    """TestClient with seeded experiment data."""
    app = create_app(seeded_tracker, registry)
    return TestClient(app)


# ---------------------------------------------------------------------------
# HTML serving
# ---------------------------------------------------------------------------


class TestHTMLServing:
    """Tests that the dashboard HTML page serves correctly."""

    def test_index_returns_200(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_is_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]

    def test_index_contains_expected_elements(self, client: TestClient) -> None:
        resp = client.get("/")
        html = resp.text
        assert "kailash-ml" in html
        assert "Experiments" in html
        assert "Models" in html
        assert "plotly" in html


# ---------------------------------------------------------------------------
# Experiments API
# ---------------------------------------------------------------------------


class TestExperimentsAPI:
    """Tests for GET /api/experiments."""

    def test_list_experiments_empty(self, client: TestClient) -> None:
        resp = client.get("/api/experiments")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_experiments_with_data(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/experiments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "my-experiment"
        assert data[0]["run_count"] == 2
        assert data[0]["latest_run_status"] == "COMPLETED"

    def test_experiment_has_required_fields(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/experiments")
        exp = resp.json()[0]
        assert "id" in exp
        assert "name" in exp
        assert "created_at" in exp
        assert "run_count" in exp
        assert "latest_run_status" in exp


# ---------------------------------------------------------------------------
# Runs API
# ---------------------------------------------------------------------------


class TestRunsAPI:
    """Tests for runs-related endpoints."""

    def test_list_runs_for_experiment(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/experiments/my-experiment/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {r["name"] for r in data}
        assert "run-alpha" in names
        assert "run-beta" in names

    def test_list_runs_not_found(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/experiments/nonexistent/runs")
        assert resp.status_code == 404

    def test_get_run_detail(
        self, seeded_client: TestClient, seeded_tracker: ExperimentTracker
    ) -> None:
        run_id = seeded_tracker._test_run_ids[0]  # type: ignore[attr-defined]
        resp = seeded_client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        run = resp.json()
        assert run["id"] == run_id
        assert run["name"] == "run-alpha"
        assert run["status"] == "COMPLETED"
        assert run["params"]["lr"] == "0.01"
        assert run["params"]["epochs"] == "10"
        # Latest metrics
        assert run["metrics"]["loss"] == pytest.approx(0.2)
        assert run["metrics"]["accuracy"] == pytest.approx(0.90)
        # Artifacts
        assert "model.pkl" in run["artifacts"]

    def test_get_run_not_found(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/runs/nonexistent-id")
        assert resp.status_code == 404

    def test_run_has_timing_fields(
        self, seeded_client: TestClient, seeded_tracker: ExperimentTracker
    ) -> None:
        run_id = seeded_tracker._test_run_ids[0]  # type: ignore[attr-defined]
        resp = seeded_client.get(f"/api/runs/{run_id}")
        run = resp.json()
        assert run["start_time"] is not None
        assert run["end_time"] is not None


# ---------------------------------------------------------------------------
# Metric history API
# ---------------------------------------------------------------------------


class TestMetricHistoryAPI:
    """Tests for GET /api/runs/{run_id}/metrics/{key}."""

    def test_metric_history(
        self, seeded_client: TestClient, seeded_tracker: ExperimentTracker
    ) -> None:
        run_id = seeded_tracker._test_run_ids[0]  # type: ignore[attr-defined]
        resp = seeded_client.get(f"/api/runs/{run_id}/metrics/loss")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        # Ordered by step
        assert data[0]["step"] == 0
        assert data[0]["value"] == pytest.approx(0.9)
        assert data[1]["step"] == 1
        assert data[1]["value"] == pytest.approx(0.5)
        assert data[2]["step"] == 2
        assert data[2]["value"] == pytest.approx(0.2)

    def test_metric_history_empty(
        self, seeded_client: TestClient, seeded_tracker: ExperimentTracker
    ) -> None:
        run_id = seeded_tracker._test_run_ids[0]  # type: ignore[attr-defined]
        resp = seeded_client.get(f"/api/runs/{run_id}/metrics/nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_metric_history_run_not_found(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/runs/bad-id/metrics/loss")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Compare API
# ---------------------------------------------------------------------------


class TestCompareAPI:
    """Tests for GET /api/compare."""

    def test_compare_runs(
        self, seeded_client: TestClient, seeded_tracker: ExperimentTracker
    ) -> None:
        ids = seeded_tracker._test_run_ids  # type: ignore[attr-defined]
        resp = seeded_client.get(f"/api/compare?run_ids={ids[0]},{ids[1]}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_ids"] == ids
        assert len(data["run_names"]) == 2
        # Params aligned
        assert "lr" in data["params"]
        assert data["params"]["lr"] == ["0.01", "0.001"]
        assert data["params"]["epochs"] == ["10", "20"]
        # Metrics aligned
        assert "loss" in data["metrics"]
        assert "accuracy" in data["metrics"]

    def test_compare_missing_param(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/compare")
        assert resp.status_code == 400

    def test_compare_too_few_ids(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/compare?run_ids=single-id")
        assert resp.status_code == 400

    def test_compare_run_not_found(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/compare?run_ids=bad1,bad2")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete run API
# ---------------------------------------------------------------------------


class TestDeleteRunAPI:
    """Tests for DELETE /api/runs/{run_id}."""

    def test_delete_run(
        self, seeded_client: TestClient, seeded_tracker: ExperimentTracker
    ) -> None:
        run_id = seeded_tracker._test_run_ids[0]  # type: ignore[attr-defined]
        resp = seeded_client.delete(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": run_id}

        # Verify deletion -- run should no longer appear
        resp2 = seeded_client.get(f"/api/runs/{run_id}")
        assert resp2.status_code == 404

    def test_delete_run_not_found(self, seeded_client: TestClient) -> None:
        resp = seeded_client.delete("/api/runs/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Models API
# ---------------------------------------------------------------------------


class TestModelsAPI:
    """Tests for model registry endpoints."""

    def test_list_models_empty(self, client: TestClient) -> None:
        resp = client.get("/api/models")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_models_with_data(
        self, registry: ModelRegistry, seeded_client: TestClient
    ) -> None:
        # Register a model via the registry engine
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            registry.register_model("test-model", b"fake-model-bytes")
        )

        resp = seeded_client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        names = [m["name"] for m in data]
        assert "test-model" in names

    def test_model_versions(
        self, registry: ModelRegistry, seeded_client: TestClient
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(registry.register_model("versioned-model", b"bytes-v1"))
        loop.run_until_complete(registry.register_model("versioned-model", b"bytes-v2"))

        resp = seeded_client.get("/api/models/versioned-model/versions")
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 2
        # Newest first
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

    def test_model_versions_nonexistent_returns_empty(
        self, seeded_client: TestClient
    ) -> None:
        """get_model_versions returns empty list for unknown models (no error)."""
        resp = seeded_client.get("/api/models/nonexistent/versions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_models_no_registry(self, tracker: ExperimentTracker) -> None:
        """When registry is None, models endpoint returns empty list."""
        app = create_app(tracker, registry=None)
        c = TestClient(app)
        resp = c.get("/api/models")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_model_versions_no_registry(self, tracker: ExperimentTracker) -> None:
        """When registry is None, versions endpoint returns 404."""
        app = create_app(tracker, registry=None)
        c = TestClient(app)
        resp = c.get("/api/models/anything/versions")
        assert resp.status_code == 404
