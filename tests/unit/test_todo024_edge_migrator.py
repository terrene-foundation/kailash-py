"""Unit tests for TODO-024: Edge Migration real implementations."""

import asyncio
import gzip
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from kailash.edge.migration.edge_migrator import (
    EdgeMigrator,
    MigrationPhase,
    MigrationStrategy,
)


@pytest.fixture
def migrator():
    """Create an EdgeMigrator with mock edge endpoints."""
    return EdgeMigrator(
        checkpoint_interval=1,
        sync_batch_size=64,
        enable_compression=True,
        edge_endpoints={
            "edge-src": "http://src.edge.local:8080",
            "edge-tgt": "http://tgt.edge.local:8080",
        },
        http_timeout=5,
    )


class _FakeResponse:
    """Minimal fake aiohttp response."""

    def __init__(self, status, json_data=None, body=b""):
        self.status = status
        self._json_data = json_data
        self._body = body

    async def json(self):
        return self._json_data

    async def text(self):
        return json.dumps(self._json_data) if self._json_data else ""

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeSession:
    """Fake aiohttp.ClientSession that records calls and returns configurable responses."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._pick(url)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._pick(url)

    def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return self._pick(url)

    def _pick(self, url):
        for pattern, resp in self.responses.items():
            if pattern in url:
                return resp
        # Default 200 with empty JSON
        return _FakeResponse(200, json_data={})

    async def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# Tests for _estimate_data_size
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_data_size_from_api(migrator):
    """Should sum sizes from the edge API for each workload."""
    session = _FakeSession(
        {
            "/size": _FakeResponse(200, {"size_bytes": 5000}),
        }
    )
    migrator._session = session

    result = await migrator._estimate_data_size("edge-src", ["wl1", "wl2"])
    assert result == 10000  # 5000 * 2 workloads


@pytest.mark.asyncio
async def test_estimate_data_size_fallback(migrator):
    """Falls back to 100 MB per workload when endpoint unreachable."""
    session = _FakeSession(
        {
            "/size": _FakeResponse(500),
        }
    )
    migrator._session = session

    result = await migrator._estimate_data_size("edge-src", ["wl1"])
    assert result == 100 * 1024 * 1024


@pytest.mark.asyncio
async def test_estimate_data_size_no_endpoint(migrator):
    """Falls back when edge is not registered in endpoints."""
    result = await migrator._estimate_data_size("unknown-edge", ["wl1"])
    assert result == 100 * 1024 * 1024


# ---------------------------------------------------------------------------
# Tests for _compress_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_data(migrator):
    """Should produce valid gzip output."""
    original = b"hello world" * 100
    compressed = await migrator._compress_data(original)
    assert gzip.decompress(compressed) == original
    assert len(compressed) < len(original)


# ---------------------------------------------------------------------------
# Tests for _check_edge_capacity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_edge_capacity(migrator):
    session = _FakeSession(
        {
            "/capacity": _FakeResponse(200, {"available_capacity": 42.5}),
        }
    )
    migrator._session = session

    cap = await migrator._check_edge_capacity("edge-tgt")
    assert cap == 42.5


@pytest.mark.asyncio
async def test_check_edge_capacity_failure(migrator):
    session = _FakeSession(
        {
            "/capacity": _FakeResponse(503),
        }
    )
    migrator._session = session

    cap = await migrator._check_edge_capacity("edge-tgt")
    assert cap == 0.0


# ---------------------------------------------------------------------------
# Tests for _calculate_required_capacity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_required_capacity_defaults(migrator):
    result = await migrator._calculate_required_capacity(["a", "b", "c"])
    assert result == 30.0


@pytest.mark.asyncio
async def test_calculate_required_capacity_custom(migrator):
    migrator.edge_resources["a"] = {"capacity_units": 5.0}
    result = await migrator._calculate_required_capacity(["a", "b"])
    assert result == 15.0  # 5.0 + 10.0


# ---------------------------------------------------------------------------
# Tests for _transfer_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transfer_batch_success(migrator):
    session = _FakeSession(
        {
            "/data": _FakeResponse(201),
        }
    )
    migrator._session = session

    await migrator._transfer_batch("edge-src", "edge-tgt", "wl1", b"payload")
    assert migrator.bandwidth_usage["edge-src->edge-tgt"] == len(b"payload")


@pytest.mark.asyncio
async def test_transfer_batch_failure(migrator):
    session = _FakeSession(
        {
            "/data": _FakeResponse(500, {"error": "disk full"}),
        }
    )
    migrator._session = session

    with pytest.raises(RuntimeError, match="Batch transfer"):
        await migrator._transfer_batch("edge-src", "edge-tgt", "wl1", b"payload")


# ---------------------------------------------------------------------------
# Tests for _verify_workload_running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_workload_running_yes(migrator):
    session = _FakeSession(
        {
            "/status": _FakeResponse(200, {"status": "running"}),
        }
    )
    migrator._session = session

    assert await migrator._verify_workload_running("edge-tgt", "wl1") is True


@pytest.mark.asyncio
async def test_verify_workload_running_stopped(migrator):
    session = _FakeSession(
        {
            "/status": _FakeResponse(200, {"status": "stopped"}),
        }
    )
    migrator._session = session

    assert await migrator._verify_workload_running("edge-tgt", "wl1") is False


# ---------------------------------------------------------------------------
# Tests for _verify_data_integrity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_data_integrity_match(migrator):
    session = _FakeSession(
        {
            "/checksum": _FakeResponse(200, {"sha256": "abc123"}),
        }
    )
    migrator._session = session

    result = await migrator._verify_data_integrity("edge-src", "edge-tgt", "wl1")
    assert result is True


@pytest.mark.asyncio
async def test_verify_data_integrity_mismatch(migrator):
    call_count = 0

    class _ToggleSession(_FakeSession):
        def get(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            self.calls.append(("GET", url, kwargs))
            if call_count == 1:
                return _FakeResponse(200, {"sha256": "aaa"})
            return _FakeResponse(200, {"sha256": "bbb"})

    session = _ToggleSession()
    migrator._session = session

    result = await migrator._verify_data_integrity("edge-src", "edge-tgt", "wl1")
    assert result is False


# ---------------------------------------------------------------------------
# Tests for _test_workload_functionality
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workload_functionality_healthy(migrator):
    session = _FakeSession(
        {
            "/health": _FakeResponse(200, {"healthy": True}),
        }
    )
    migrator._session = session

    assert await migrator._test_workload_functionality("edge-tgt", "wl1") is True


# ---------------------------------------------------------------------------
# Tests for _restore_from_checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_from_checkpoint(migrator):
    plan = await migrator.plan_migration(
        "edge-src", "edge-tgt", ["wl1"], strategy=MigrationStrategy.LIVE
    )
    mid = plan.migration_id
    progress = migrator.migration_progress[mid]
    progress.phase = MigrationPhase.SYNC
    progress.progress_percent = 50.0
    progress.data_transferred = 1000

    checkpoint = await migrator._create_checkpoint(mid, MigrationPhase.SYNC)

    # Modify progress
    progress.phase = MigrationPhase.CUTOVER
    progress.progress_percent = 80.0

    # Restore
    await migrator._restore_from_checkpoint(checkpoint)

    assert progress.phase == MigrationPhase.SYNC
    assert progress.progress_percent == 50.0


# ---------------------------------------------------------------------------
# Tests for _cleanup_temp_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_temp_data(migrator):
    migrator._source_checksums["mig-1"]["wl1"] = "abc"
    migrator._temp_data["mig-1"] = ["/tmp/foo"]

    await migrator._cleanup_temp_data("mig-1")

    assert "mig-1" not in migrator._source_checksums
    assert "mig-1" not in migrator._temp_data


# ---------------------------------------------------------------------------
# Tests for _get_workload_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_workload_data_batching(migrator):
    """Returned data should be split into sync_batch_size chunks."""
    raw = b"x" * 200  # 200 bytes, batch_size = 64
    session = _FakeSession(
        {
            "/data": _FakeResponse(200, body=raw),
        }
    )
    migrator._session = session

    batches = await migrator._get_workload_data("edge-src", "wl1")
    assert len(batches) == 4  # ceil(200 / 64) = 4
    assert b"".join(batches) == raw


# ---------------------------------------------------------------------------
# Tests for _switch_traffic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_switch_traffic(migrator):
    session = _FakeSession(
        {
            "/routing": _FakeResponse(200),
        }
    )
    migrator._session = session

    await migrator._switch_traffic("edge-src", "edge-tgt", ["wl1"])

    # Should have called routing endpoint on both source and target
    routing_calls = [c for c in session.calls if "/routing" in c[1]]
    assert len(routing_calls) == 2


# ---------------------------------------------------------------------------
# Tests for _drain_source_edge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drain_source_edge(migrator):
    session = _FakeSession(
        {
            "/drain": _FakeResponse(200),
        }
    )
    migrator._session = session

    await migrator._drain_source_edge("edge-src", ["wl1", "wl2"])

    drain_calls = [c for c in session.calls if "/drain" in c[1]]
    assert len(drain_calls) == 2


# ---------------------------------------------------------------------------
# Validate plan checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_plan_same_source_target(migrator):
    with pytest.raises(ValueError, match="Source and target must be different"):
        await migrator.plan_migration("edge-src", "edge-src", ["wl1"])


@pytest.mark.asyncio
async def test_validate_plan_no_workloads(migrator):
    with pytest.raises(ValueError, match="No workloads specified"):
        await migrator.plan_migration("edge-src", "edge-tgt", [])
