# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for FileSourceAdapter directory scanning (#249).

Tests: latest by name, latest by mtime, empty directory, pattern matching,
change detection with new files, single-file backward compatibility.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from dataflow.fabric.config import FileSourceConfig
from dataflow.adapters.file_adapter import FileSourceAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scan_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with dated ledger files."""
    d = tmp_path / "ledgers"
    d.mkdir()
    # Create files with deterministic names and content
    for name in [
        "ledger_2026-01-01.json",
        "ledger_2026-02-15.json",
        "ledger_2026-03-20.json",
    ]:
        (d / name).write_text('{"date": "' + name + '"}', encoding="utf-8")
    return d


@pytest.fixture
def single_file(tmp_path: Path) -> Path:
    """Create a single JSON file for backward-compat tests."""
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}', encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestFileSourceConfigValidation:
    def test_path_only_valid(self, single_file: Path):
        cfg = FileSourceConfig(path=str(single_file))
        cfg.validate()  # Should not raise

    def test_directory_only_valid(self, scan_dir: Path):
        cfg = FileSourceConfig(directory=str(scan_dir), pattern="ledger_*.json")
        cfg.validate()  # Should not raise

    def test_both_path_and_directory_raises(self, single_file: Path, scan_dir: Path):
        cfg = FileSourceConfig(
            path=str(single_file), directory=str(scan_dir), pattern="*.json"
        )
        with pytest.raises(ValueError, match="not both"):
            cfg.validate()

    def test_neither_path_nor_directory_raises(self):
        cfg = FileSourceConfig()
        with pytest.raises(ValueError, match="must be set"):
            cfg.validate()

    def test_directory_without_pattern_raises(self, scan_dir: Path):
        cfg = FileSourceConfig(directory=str(scan_dir))
        with pytest.raises(ValueError, match="pattern.*required"):
            cfg.validate()

    def test_invalid_selection_raises(self, scan_dir: Path):
        cfg = FileSourceConfig(
            directory=str(scan_dir), pattern="*.json", selection="newest"
        )
        with pytest.raises(ValueError, match="selection"):
            cfg.validate()


# ---------------------------------------------------------------------------
# Directory scanning — latest by name
# ---------------------------------------------------------------------------


class TestDirectoryScanningByName:
    @pytest.mark.asyncio
    async def test_selects_latest_by_name(self, scan_dir: Path):
        cfg = FileSourceConfig(
            directory=str(scan_dir),
            pattern="ledger_*.json",
            selection="latest_name",
            watch=False,
        )
        adapter = FileSourceAdapter("test_dir", cfg)
        await adapter.connect()

        # Lexicographic sort: ledger_2026-03-20.json is last
        assert adapter._resolved_path is not None
        assert adapter._resolved_path.name == "ledger_2026-03-20.json"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_fetch_returns_latest_file_content(self, scan_dir: Path):
        cfg = FileSourceConfig(
            directory=str(scan_dir),
            pattern="ledger_*.json",
            selection="latest_name",
            watch=False,
        )
        adapter = FileSourceAdapter("test_dir", cfg)
        await adapter.connect()

        data = await adapter.fetch()
        assert data["date"] == "ledger_2026-03-20.json"

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Directory scanning — latest by mtime
# ---------------------------------------------------------------------------


class TestDirectoryScanningByMtime:
    @pytest.mark.asyncio
    async def test_selects_latest_by_mtime(self, scan_dir: Path):
        # Set mtimes so the middle file is actually newest
        oldest = scan_dir / "ledger_2026-03-20.json"
        middle = scan_dir / "ledger_2026-01-01.json"
        newest = scan_dir / "ledger_2026-02-15.json"

        base_time = time.time()
        os.utime(oldest, (base_time - 200, base_time - 200))
        os.utime(middle, (base_time - 100, base_time - 100))
        os.utime(newest, (base_time, base_time))

        cfg = FileSourceConfig(
            directory=str(scan_dir),
            pattern="ledger_*.json",
            selection="latest_mtime",
            watch=False,
        )
        adapter = FileSourceAdapter("test_mtime", cfg)
        await adapter.connect()

        assert adapter._resolved_path is not None
        assert adapter._resolved_path.name == "ledger_2026-02-15.json"

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Empty directory
# ---------------------------------------------------------------------------


class TestEmptyDirectory:
    @pytest.mark.asyncio
    async def test_empty_directory_raises_file_not_found(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()

        cfg = FileSourceConfig(
            directory=str(empty),
            pattern="*.json",
            watch=False,
        )
        adapter = FileSourceAdapter("test_empty", cfg)

        with pytest.raises(FileNotFoundError, match="No files matching"):
            await adapter.connect()


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------


class TestPatternMatching:
    @pytest.mark.asyncio
    async def test_pattern_filters_correctly(self, scan_dir: Path):
        # Add a non-matching file
        (scan_dir / "readme.txt").write_text("not a ledger", encoding="utf-8")
        (scan_dir / "other_2026-04-01.json").write_text('{"x": 1}', encoding="utf-8")

        cfg = FileSourceConfig(
            directory=str(scan_dir),
            pattern="ledger_*.json",
            selection="latest_name",
            watch=False,
        )
        adapter = FileSourceAdapter("test_pattern", cfg)
        await adapter.connect()

        # Should only match ledger_ files, not readme.txt or other_
        assert adapter._resolved_path is not None
        assert adapter._resolved_path.name == "ledger_2026-03-20.json"

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Change detection — directory mode
# ---------------------------------------------------------------------------


class TestDirectoryChangeDetection:
    @pytest.mark.asyncio
    async def test_new_file_detected(self, scan_dir: Path):
        cfg = FileSourceConfig(
            directory=str(scan_dir),
            pattern="ledger_*.json",
            selection="latest_name",
            watch=False,
        )
        adapter = FileSourceAdapter("test_change", cfg)
        await adapter.connect()

        # Initially points to ledger_2026-03-20
        assert adapter._resolved_path.name == "ledger_2026-03-20.json"

        # No change yet
        changed = await adapter.detect_change()
        assert changed is False

        # Add a newer file (lexicographically after 03-20)
        new_file = scan_dir / "ledger_2026-04-01.json"
        new_file.write_text('{"date": "2026-04-01"}', encoding="utf-8")

        # Now detect_change should find the new file
        changed = await adapter.detect_change()
        assert changed is True
        assert adapter._resolved_path.name == "ledger_2026-04-01.json"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_no_new_file_no_change(self, scan_dir: Path):
        cfg = FileSourceConfig(
            directory=str(scan_dir),
            pattern="ledger_*.json",
            selection="latest_name",
            watch=False,
        )
        adapter = FileSourceAdapter("test_nochange", cfg)
        await adapter.connect()

        changed = await adapter.detect_change()
        assert changed is False

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_existing_file_modified_detected(self, scan_dir: Path):
        cfg = FileSourceConfig(
            directory=str(scan_dir),
            pattern="ledger_*.json",
            selection="latest_name",
            watch=False,
        )
        adapter = FileSourceAdapter("test_modify", cfg)
        await adapter.connect()

        # Modify the current latest file
        target = scan_dir / "ledger_2026-03-20.json"
        # Ensure mtime changes (some filesystems have 1s resolution)
        time.sleep(0.05)
        target.write_text('{"date": "modified"}', encoding="utf-8")
        # Force mtime to be different
        os.utime(target, (time.time() + 10, time.time() + 10))

        changed = await adapter.detect_change()
        assert changed is True

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Single-file backward compatibility
# ---------------------------------------------------------------------------


class TestSingleFileBackwardCompat:
    @pytest.mark.asyncio
    async def test_single_file_still_works(self, single_file: Path):
        cfg = FileSourceConfig(path=str(single_file), watch=False)
        adapter = FileSourceAdapter("test_single", cfg)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == {"key": "value"}

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_single_file_detect_change(self, single_file: Path):
        cfg = FileSourceConfig(path=str(single_file), watch=False)
        adapter = FileSourceAdapter("test_single_change", cfg)
        await adapter.connect()

        # No change initially
        changed = await adapter.detect_change()
        assert changed is False

        # Modify the file
        time.sleep(0.05)
        single_file.write_text('{"key": "updated"}', encoding="utf-8")
        os.utime(single_file, (time.time() + 10, time.time() + 10))

        changed = await adapter.detect_change()
        assert changed is True

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_single_file_missing_raises(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.json"
        cfg = FileSourceConfig(path=str(missing), watch=False)
        adapter = FileSourceAdapter("test_missing", cfg)

        with pytest.raises(FileNotFoundError, match="does not exist"):
            await adapter.connect()
