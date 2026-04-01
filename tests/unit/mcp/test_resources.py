# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ResourceCache (MCP-507)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

# The kailash.mcp.__init__ imports from a Rust native module (kailash._kailash).
# When the native module is not built, we need to import ResourceCache by path
# manipulation to avoid the __init__ import chain.
try:
    from kailash.mcp.resources import ResourceCache
except (ImportError, ModuleNotFoundError):
    # Direct import bypassing the package __init__
    import importlib.util
    import sys
    from pathlib import Path as _Path

    _spec = importlib.util.spec_from_file_location(
        "kailash.mcp.resources",
        _Path(__file__).resolve().parents[3]
        / "src"
        / "kailash"
        / "mcp"
        / "resources.py",
    )
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["kailash.mcp.resources"] = _mod
        _spec.loader.exec_module(_mod)
        ResourceCache = _mod.ResourceCache  # type: ignore[assignment]
    else:
        pytest.skip("Cannot import ResourceCache", allow_module_level=True)


class TestResourceCache:
    """Tests for the mtime-based ResourceCache."""

    def test_caches_data_on_first_call(self, tmp_path: Path):
        """First call builds and caches data."""
        cache = ResourceCache(tmp_path)
        call_count = 0

        def builder():
            nonlocal call_count
            call_count += 1
            return {"items": [1, 2, 3]}

        result = cache.get_or_refresh("test://uri", builder)
        assert result == {"items": [1, 2, 3]}
        assert call_count == 1

    def test_returns_cached_on_second_call(self, tmp_path: Path):
        """Second call returns cached data without rebuilding."""
        cache = ResourceCache(tmp_path)
        call_count = 0

        def builder():
            nonlocal call_count
            call_count += 1
            return {"data": "value"}

        cache.get_or_refresh("test://uri", builder)
        result = cache.get_or_refresh("test://uri", builder)
        assert result == {"data": "value"}
        assert call_count == 1  # Not rebuilt

    def test_invalidates_on_mtime_change(self, tmp_path: Path):
        """Cache is rebuilt when a file mtime changes."""
        # Create a Python file
        py_file = tmp_path / "app.py"
        py_file.write_text("x = 1", encoding="utf-8")

        cache = ResourceCache(tmp_path)
        call_count = 0

        def builder():
            nonlocal call_count
            call_count += 1
            return {"version": call_count}

        # First call
        result1 = cache.get_or_refresh("test://uri", builder)
        assert result1 == {"version": 1}

        # Modify the file (bump mtime)
        time.sleep(0.05)  # Ensure mtime differs
        py_file.write_text("x = 2", encoding="utf-8")

        # Second call should rebuild
        result2 = cache.get_or_refresh("test://uri", builder)
        assert result2 == {"version": 2}
        assert call_count == 2

    def test_different_uris_cached_separately(self, tmp_path: Path):
        """Different URIs maintain separate cache entries."""
        cache = ResourceCache(tmp_path)

        result_a = cache.get_or_refresh("uri://a", lambda: "data_a")
        result_b = cache.get_or_refresh("uri://b", lambda: "data_b")

        assert result_a == "data_a"
        assert result_b == "data_b"

    def test_invalidate_single_uri(self, tmp_path: Path):
        """Invalidating a single URI forces rebuild."""
        cache = ResourceCache(tmp_path)
        call_count = 0

        def builder():
            nonlocal call_count
            call_count += 1
            return call_count

        cache.get_or_refresh("test://uri", builder)
        cache.invalidate("test://uri")
        result = cache.get_or_refresh("test://uri", builder)
        assert result == 2

    def test_invalidate_all(self, tmp_path: Path):
        """Invalidating all URIs clears the entire cache."""
        cache = ResourceCache(tmp_path)
        cache.get_or_refresh("uri://a", lambda: "a")
        cache.get_or_refresh("uri://b", lambda: "b")
        cache.invalidate()

        calls = []

        def track_builder(val):
            def _build():
                calls.append(val)
                return val

            return _build

        cache.get_or_refresh("uri://a", track_builder("a2"))
        cache.get_or_refresh("uri://b", track_builder("b2"))
        assert len(calls) == 2

    def test_thread_safety(self, tmp_path: Path):
        """Concurrent access does not corrupt cache state."""
        cache = ResourceCache(tmp_path)
        results: list[int] = []
        counter = {"v": 0}
        lock = threading.Lock()

        def builder():
            with lock:
                counter["v"] += 1
                return counter["v"]

        def worker():
            val = cache.get_or_refresh("test://concurrent", builder)
            results.append(val)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should be the same value (cached)
        assert len(set(results)) == 1

    def test_empty_project_no_crash(self, tmp_path: Path):
        """ResourceCache works on empty directories."""
        cache = ResourceCache(tmp_path)
        result = cache.get_or_refresh("test://empty", lambda: [])
        assert result == []

    def test_skips_hidden_dirs(self, tmp_path: Path):
        """Files in .hidden and __pycache__ directories are skipped."""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x = 1", encoding="utf-8")

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.cpython-312.pyc").write_text("x", encoding="utf-8")

        cache = ResourceCache(tmp_path)
        # Should still work (max_mtime from scanning)
        result = cache.get_or_refresh("test://hidden", lambda: "ok")
        assert result == "ok"
