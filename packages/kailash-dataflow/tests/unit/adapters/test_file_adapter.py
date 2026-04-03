# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tests for FileSourceAdapter — Tier 2 (real temp files, no mocking).

Validates:
- Connection lifecycle (connect, disconnect, state transitions)
- File parsing (.json, .yaml, .csv, raw text)
- Change detection via mtime polling
- Write operations with read-back verification
- Paginated fetch for CSV
- Path security (M4: reject '..', path traversal)
- Parser override via config.parser
- Error handling (missing files, unreadable files, disconnected state)
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from dataflow.adapters.file_adapter import FileSourceAdapter, _validate_file_path
from dataflow.adapters.source_adapter import SourceState
from dataflow.fabric.config import FileSourceConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for test files."""
    return tmp_path


def _write_file(directory: Path, name: str, content: str) -> Path:
    """Write a text file and return its path."""
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_adapter(
    file_path: str, *, watch: bool = False, parser: str | None = None
) -> FileSourceAdapter:
    """Create a FileSourceAdapter with the given config."""
    config = FileSourceConfig(path=file_path, watch=watch, parser=parser)
    return FileSourceAdapter(name="test_file", config=config)


# ---------------------------------------------------------------------------
# Path security tests (M4)
# ---------------------------------------------------------------------------


class TestPathSecurity:
    """Tests for _validate_file_path security enforcement."""

    def test_empty_path_rejected(self) -> None:
        assert_raises_value_error("", "must not be empty")

    def test_path_resolved_to_absolute(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", "{}")
        resolved = _validate_file_path(str(f))
        assert resolved.is_absolute()

    def test_path_outside_base_dir_rejected(self, tmp_dir: Path) -> None:
        other = tmp_dir / "other"
        other.mkdir()
        f = _write_file(other, "data.json", "{}")
        base = tmp_dir / "confined"
        base.mkdir()

        with pytest.raises(ValueError, match="outside the allowed base directory"):
            _validate_file_path(str(f), base)

    def test_path_within_base_dir_accepted(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", "{}")
        resolved = _validate_file_path(str(f), tmp_dir)
        assert resolved == f.resolve()


def assert_raises_value_error(raw: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _validate_file_path(raw)


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    """Tests for connect/disconnect and state transitions."""

    @pytest.mark.asyncio
    async def test_connect_sets_active_state(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", '{"key": "value"}')
        adapter = _make_adapter(str(f), watch=False)

        assert adapter.state == SourceState.REGISTERED
        await adapter.connect()

        assert adapter.state == SourceState.ACTIVE
        assert adapter.is_connected is True
        assert adapter.database_type == "file"

        await adapter.disconnect()
        assert adapter.state == SourceState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_connect_missing_file_raises(self, tmp_dir: Path) -> None:
        adapter = _make_adapter(str(tmp_dir / "nonexistent.json"), watch=False)

        with pytest.raises(FileNotFoundError, match="does not exist"):
            await adapter.connect()

        assert adapter.state == SourceState.ERROR

    @pytest.mark.asyncio
    async def test_connect_empty_path_config_raises(self) -> None:
        config = FileSourceConfig(path="", watch=False)
        adapter = FileSourceAdapter(name="bad", config=config)

        with pytest.raises(ValueError, match="must not be empty"):
            await adapter.connect()


# ---------------------------------------------------------------------------
# Fetch — JSON
# ---------------------------------------------------------------------------


class TestFetchJSON:
    """Tests for JSON file reading."""

    @pytest.mark.asyncio
    async def test_fetch_json_dict(self, tmp_dir: Path) -> None:
        payload = {"users": [{"id": 1, "name": "Alice"}]}
        f = _write_file(tmp_dir, "data.json", json.dumps(payload))
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == payload

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_fetch_json_list(self, tmp_dir: Path) -> None:
        payload = [1, 2, 3]
        f = _write_file(tmp_dir, "data.json", json.dumps(payload))
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == payload

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Fetch — YAML
# ---------------------------------------------------------------------------


class TestFetchYAML:
    """Tests for YAML file reading (lazy import of pyyaml)."""

    @pytest.mark.asyncio
    async def test_fetch_yaml(self, tmp_dir: Path) -> None:
        yaml_content = "name: Alice\nage: 30\nitems:\n  - a\n  - b\n"
        f = _write_file(tmp_dir, "config.yaml", yaml_content)
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == {"name": "Alice", "age": 30, "items": ["a", "b"]}

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_fetch_yml_extension(self, tmp_dir: Path) -> None:
        yml_content = "key: value\n"
        f = _write_file(tmp_dir, "config.yml", yml_content)
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == {"key": "value"}

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Fetch — CSV
# ---------------------------------------------------------------------------


class TestFetchCSV:
    """Tests for CSV file reading."""

    @pytest.mark.asyncio
    async def test_fetch_csv(self, tmp_dir: Path) -> None:
        csv_content = "name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        f = _write_file(tmp_dir, "data.csv", csv_content)
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"name": "Alice", "age": "30", "city": "NYC"}
        assert data[1] == {"name": "Bob", "age": "25", "city": "LA"}

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_fetch_csv_empty(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "empty.csv", "name,age\n")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == []

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Fetch — raw text
# ---------------------------------------------------------------------------


class TestFetchText:
    """Tests for plain text / unknown extensions."""

    @pytest.mark.asyncio
    async def test_fetch_text_file(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "readme.txt", "Hello World")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == "Hello World"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_fetch_unknown_extension(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.xyz", "raw content")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        data = await adapter.fetch()
        assert data == "raw content"

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Parser override
# ---------------------------------------------------------------------------


class TestParserOverride:
    """Tests for config.parser override."""

    @pytest.mark.asyncio
    async def test_parser_override_json_on_txt_file(self, tmp_dir: Path) -> None:
        """Force JSON parser on a .txt file."""
        payload = {"forced": True}
        f = _write_file(tmp_dir, "data.txt", json.dumps(payload))
        adapter = _make_adapter(str(f), watch=False, parser="json")
        await adapter.connect()

        data = await adapter.fetch()
        assert data == payload

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_parser_override_csv_on_txt_file(self, tmp_dir: Path) -> None:
        """Force CSV parser on a .txt file."""
        f = _write_file(tmp_dir, "data.txt", "a,b\n1,2\n3,4\n")
        adapter = _make_adapter(str(f), watch=False, parser="csv")
        await adapter.connect()

        data = await adapter.fetch()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"a": "1", "b": "2"}

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Change detection (mtime polling)
# ---------------------------------------------------------------------------


class TestChangeDetection:
    """Tests for mtime-based change detection."""

    @pytest.mark.asyncio
    async def test_no_change_detected_initially(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", "{}")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        changed = await adapter.detect_change()
        assert changed is False

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_change_detected_after_modification(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", '{"v": 1}')
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        # Ensure mtime advances (some filesystems have 1s granularity)
        time.sleep(0.05)
        f.write_text('{"v": 2}', encoding="utf-8")
        # Force mtime change on filesystems with coarse granularity
        new_mtime = adapter._last_mtime + 1.0
        os.utime(f, (new_mtime, new_mtime))

        changed = await adapter.detect_change()
        assert changed is True

        # Second check should show no change
        changed2 = await adapter.detect_change()
        assert changed2 is False

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_detect_change_before_connect_raises(self) -> None:
        config = FileSourceConfig(path="/tmp/doesnt_matter.json", watch=False)
        adapter = FileSourceAdapter(name="unconnected", config=config)

        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.detect_change()

    @pytest.mark.asyncio
    async def test_detect_change_file_deleted(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", "{}")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        f.unlink()
        changed = await adapter.detect_change()
        assert changed is False  # graceful — logs warning, returns False

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


class TestWrite:
    """Tests for file writing with read-back verification."""

    @pytest.mark.asyncio
    async def test_write_dict_as_json(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "output.json", "{}")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        payload = {"written": True, "count": 42}
        result = await adapter.write("", payload)

        assert result["bytes_written"] > 0
        assert result["path"] == str(f.resolve())

        # Read back to verify persistence
        read_data = await adapter.fetch()
        assert read_data == payload

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_write_list_as_json(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "output.json", "[]")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        payload = [{"id": 1}, {"id": 2}]
        await adapter.write("", payload)

        read_data = await adapter.fetch()
        assert read_data == payload

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_write_string(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "output.txt", "")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        await adapter.write("", "plain text content")

        read_data = await adapter.fetch()
        assert read_data == "plain text content"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_write_to_alternate_path(self, tmp_dir: Path) -> None:
        """Write to a different file within the base directory."""
        main_file = _write_file(tmp_dir, "main.json", "{}")
        alt_file = tmp_dir / "alt.json"
        alt_file.write_text("{}", encoding="utf-8")

        adapter = _make_adapter(str(main_file), watch=False)
        await adapter.connect()

        payload = {"alt": True}
        await adapter.write(str(alt_file), payload)

        # Verify via direct read
        assert json.loads(alt_file.read_text(encoding="utf-8")) == payload

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Paginated fetch
# ---------------------------------------------------------------------------


class TestFetchPages:
    """Tests for fetch_pages (chunked reading)."""

    @pytest.mark.asyncio
    async def test_csv_pagination(self, tmp_dir: Path) -> None:
        rows = "id,name\n" + "".join(f"{i},name_{i}\n" for i in range(10))
        f = _write_file(tmp_dir, "data.csv", rows)
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        pages: list[list[Any]] = []
        async for page in adapter.fetch_pages("", page_size=3):
            pages.append(page)

        # 10 rows / 3 per page = 4 pages (3, 3, 3, 1)
        assert len(pages) == 4
        assert len(pages[0]) == 3
        assert len(pages[3]) == 1
        assert pages[0][0]["id"] == "0"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_json_list_pagination(self, tmp_dir: Path) -> None:
        payload = list(range(7))
        f = _write_file(tmp_dir, "data.json", json.dumps(payload))
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        pages: list[list[Any]] = []
        async for page in adapter.fetch_pages("", page_size=3):
            pages.append(page)

        # 7 items / 3 = 3 pages (3, 3, 1)
        assert len(pages) == 3
        assert pages[0] == [0, 1, 2]
        assert pages[2] == [6]

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_text_file_single_page(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.txt", "hello world")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        pages: list[list[Any]] = []
        async for page in adapter.fetch_pages("", page_size=100):
            pages.append(page)

        assert len(pages) == 1
        assert pages[0] == ["hello world"]

        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Health check and features
# ---------------------------------------------------------------------------


class TestHealthAndFeatures:
    """Tests for health_check and supports_feature."""

    @pytest.mark.asyncio
    async def test_health_check(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", "{}")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        health = await adapter.health_check()
        assert health["healthy"] is True
        assert health["source_type"] == "file"
        assert health["state"] == "active"

        await adapter.disconnect()

    def test_supports_feature(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", "{}")
        adapter = _make_adapter(str(f), watch=False)

        assert adapter.supports_feature("detect_change") is True
        assert adapter.supports_feature("fetch") is True
        assert adapter.supports_feature("write") is True
        assert adapter.supports_feature("fetch_pages") is True
        assert adapter.supports_feature("transactions") is False


# ---------------------------------------------------------------------------
# Last successful data (graceful degradation)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Tests for last_successful_data caching."""

    @pytest.mark.asyncio
    async def test_last_successful_data_cached(self, tmp_dir: Path) -> None:
        payload = {"cached": True}
        f = _write_file(tmp_dir, "data.json", json.dumps(payload))
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        await adapter.fetch()

        last = adapter.last_successful_data("")
        assert last == payload

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_last_successful_data_none_before_fetch(self, tmp_dir: Path) -> None:
        f = _write_file(tmp_dir, "data.json", "{}")
        adapter = _make_adapter(str(f), watch=False)
        await adapter.connect()

        assert adapter.last_successful_data("") is None

        await adapter.disconnect()
