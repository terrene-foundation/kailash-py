# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W12 Tier-2 integration tests — concurrent logging + artifact dedup.

Uses a real on-disk SQLite database (via ``tmp_path``) rather than
``:memory:`` so WAL + connection-pool behaviour is exercised. Per
``rules/testing.md`` § Tier 2, no ``unittest.mock`` / ``MagicMock``.

Covers:

- 10-worker concurrent ``log_metric`` writes survive without row loss
  (append-only + asyncio.Lock serialises at the backend).
- ``log_artifact`` dedupes on SHA-256 across concurrent writers.
- ``log_figure`` plotly + matplotlib paths both materialise artifact
  bytes on disk (not just a DB row).
- ``add_tag`` / ``add_tags`` upsert survives concurrent workers.
- State-persistence verification per ``rules/testing.md`` § "State
  Persistence Verification (Tiers 2-3)": every write is read back
  through ``list_metrics`` / ``list_artifacts`` / ``list_tags``.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from kailash_ml.tracking import ExperimentTracker
from kailash_ml.tracking.runner import ArtifactHandle

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _mk_tracker(tmp_path: Path) -> ExperimentTracker:
    """Build a tracker backed by an on-disk SQLite file."""
    db_path = tmp_path / "ml.db"
    return await ExperimentTracker.create(f"sqlite:///{db_path}")


class TestConcurrentMetrics:
    async def test_10_worker_log_metric_no_row_loss(self, tmp_path: Path) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("concurrent-metrics") as run:

                async def worker(worker_id: int) -> None:
                    for step in range(50):
                        await run.log_metric(
                            f"worker_{worker_id}.loss",
                            1.0 - (step * 0.01),
                            step=step,
                        )

                await asyncio.gather(*(worker(i) for i in range(10)))
            rows = await tracker._backend.list_metrics(run.run_id)
            # 10 workers × 50 steps = 500 rows, all persisted, unique per
            # (key, step) tuple.
            assert len(rows) == 500
            seen = {(r["key"], r["step"]) for r in rows}
            assert len(seen) == 500
        finally:
            await tracker.close()

    async def test_log_metrics_batch_is_atomic(self, tmp_path: Path) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("batch") as run:
                # 20 concurrent batches, each with 5 metrics → 100 rows.
                async def batch(batch_id: int) -> None:
                    await run.log_metrics(
                        {f"b{batch_id}.m{i}": float(i) for i in range(5)},
                        step=batch_id,
                    )

                await asyncio.gather(*(batch(b) for b in range(20)))
            rows = await tracker._backend.list_metrics(run.run_id)
            assert len(rows) == 100
        finally:
            await tracker.close()


class TestArtifactDedupe:
    async def test_concurrent_identical_bytes_produce_one_row(
        self, tmp_path: Path
    ) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("dedup") as run:
                payload = b"the-same-bytes" * 100

                async def writer(i: int) -> ArtifactHandle:
                    # Same NAME + same bytes → one PK row; concurrent
                    # INSERT OR IGNORE dedupes.
                    return await run.log_artifact(payload, "shared.bin")

                handles = await asyncio.gather(*(writer(i) for i in range(8)))
            # All handles reference the same sha256 + storage_uri.
            assert len({h.sha256 for h in handles}) == 1
            assert len({h.storage_uri for h in handles}) == 1
            # Exactly one DB row.
            rows = await tracker._backend.list_artifacts(run.run_id)
            assert len(rows) == 1
            # Bytes on disk match the payload.
            stored = Path(rows[0]["storage_uri"]).read_bytes()
            assert stored == payload
        finally:
            await tracker.close()

    async def test_distinct_bytes_produce_distinct_rows(self, tmp_path: Path) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("distinct") as run:
                h1 = await run.log_artifact(b"payload-one", "a.bin")
                h2 = await run.log_artifact(b"payload-two", "b.bin")
            assert h1.sha256 != h2.sha256
            rows = await tracker._backend.list_artifacts(run.run_id)
            assert len(rows) == 2
            assert sorted(r["name"] for r in rows) == ["a.bin", "b.bin"]
        finally:
            await tracker.close()


class _FakePlotlyFig:
    def to_json(self) -> str:
        return '{"data": [{"x": [1, 2], "y": [3, 4]}], "layout": {}}'


class _FakeMatplotlibFig:
    def savefig(self, buf, *, format: str) -> None:  # noqa: ANN001
        assert format == "png"
        buf.write(b"\x89PNG\r\n\x1a\n" + b"PNG-fake-payload")


class TestFigureSink:
    async def test_plotly_figure_materialises_on_disk(self, tmp_path: Path) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("fig") as run:
                handle = await run.log_figure(_FakePlotlyFig(), "loss_curve")
            assert handle.content_type == "application/vnd.plotly.v1+json"
            # State-persistence verification: read back through the
            # list_artifacts API + the filesystem.
            rows = await tracker._backend.list_artifacts(run.run_id)
            assert len(rows) == 1
            assert rows[0]["content_type"] == "application/vnd.plotly.v1+json"
            on_disk = Path(rows[0]["storage_uri"]).read_bytes()
            assert on_disk.startswith(b"{")  # JSON
        finally:
            await tracker.close()

    async def test_matplotlib_figure_materialises_png_bytes(
        self, tmp_path: Path
    ) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("fig") as run:
                handle = await run.log_figure(_FakeMatplotlibFig(), "confmat")
            rows = await tracker._backend.list_artifacts(run.run_id)
            assert len(rows) == 1
            assert rows[0]["content_type"] == "image/png"
            on_disk = Path(rows[0]["storage_uri"]).read_bytes()
            assert on_disk.startswith(b"\x89PNG")
            assert handle.sha256 == rows[0]["sha256"]
        finally:
            await tracker.close()


class TestTagUpsertConcurrent:
    async def test_concurrent_upsert_last_writer_wins(self, tmp_path: Path) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("tags") as run:
                # 20 concurrent writers racing on env/stage.
                async def writer(i: int) -> None:
                    await run.add_tag("env", f"env_{i}")

                await asyncio.gather(*(writer(i) for i in range(20)))
            tags = await tracker._backend.list_tags(run.run_id)
            assert "env" in tags
            assert tags["env"].startswith("env_")
            # Exactly one row — PK (run_id, key) guarantees it.
            assert len(tags) == 1
        finally:
            await tracker.close()


class TestModelSnapshotRoundTrip:
    async def test_model_snapshot_reads_back(self, tmp_path: Path) -> None:
        tracker = await _mk_tracker(tmp_path)
        try:
            async with tracker.track("model-e2e") as run:
                info = await run.log_model(
                    b"\x01\x02\x03",
                    "classifier",
                    format="onnx",
                    signature={"in": "float32[1,4]", "out": "int64[1]"},
                    lineage={"dataset_hash": "sha256:cafe"},
                )
            # Read-back verifies the snapshot is persisted, the artifact
            # bytes are on disk, and the lineage JSON round-trips.
            versions = await tracker._backend.list_model_versions(run.run_id)
            assert len(versions) == 1
            row = versions[0]
            assert row["name"] == "classifier"
            assert row["format"] == "onnx"
            assert row["artifact_sha"] == info.artifact_sha
            assert "sha256:cafe" in row["lineage_json"]
            artifacts = await tracker._backend.list_artifacts(run.run_id)
            assert any(a["sha256"] == info.artifact_sha for a in artifacts)
        finally:
            await tracker.close()
