# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NexusFile transport-agnostic file parameter.

Tests NexusFile creation from paths, base64, and the read/aread methods.
Part of NTR-013 (Phase 2 feature APIs).
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest

from nexus.files import NexusFile


class TestNexusFileBasic:
    """Tests for basic NexusFile construction and access."""

    def test_defaults(self):
        f = NexusFile(filename="test.txt")
        assert f.filename == "test.txt"
        assert f.content_type == "application/octet-stream"
        assert f.size == 0
        assert f._data == b""

    def test_read(self):
        f = NexusFile(filename="test.txt", _data=b"hello world")
        assert f.read() == b"hello world"

    @pytest.mark.asyncio
    async def test_aread(self):
        f = NexusFile(filename="test.txt", _data=b"hello async")
        result = await f.aread()
        assert result == b"hello async"

    def test_to_dict(self):
        f = NexusFile(
            filename="photo.jpg",
            content_type="image/jpeg",
            size=1024,
            _data=b"\x00" * 1024,
        )
        d = f.to_dict()
        assert d == {
            "filename": "photo.jpg",
            "content_type": "image/jpeg",
            "size": 1024,
        }
        # to_dict must not include binary data
        assert "_data" not in d
        assert "data" not in d


class TestNexusFileFromPath:
    """Tests for NexusFile.from_path() factory."""

    def test_from_path_text_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"file contents here")
            f.flush()
            path = f.name

        nf = NexusFile.from_path(path)
        assert nf.filename == Path(path).name
        assert nf.content_type == "text/plain"
        assert nf.size == 18
        assert nf.read() == b"file contents here"

        # Cleanup
        Path(path).unlink()

    def test_from_path_binary_file(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            data = bytes(range(256))
            f.write(data)
            f.flush()
            path = f.name

        nf = NexusFile.from_path(path)
        assert nf.size == 256
        assert nf.read() == data

        Path(path).unlink()

    def test_from_path_accepts_path_object(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{"key": "value"}')
            f.flush()
            path = Path(f.name)

        nf = NexusFile.from_path(path)
        assert nf.filename == path.name
        assert nf.read() == b'{"key": "value"}'

        path.unlink()


class TestNexusFileFromBase64:
    """Tests for NexusFile.from_base64() factory."""

    def test_basic_decode(self):
        original = b"hello base64 world"
        encoded = base64.b64encode(original).decode("ascii")
        nf = NexusFile.from_base64(encoded, filename="test.txt")
        assert nf.filename == "test.txt"
        assert nf.read() == original
        assert nf.size == len(original)

    def test_content_type_from_filename(self):
        encoded = base64.b64encode(b"data").decode("ascii")
        nf = NexusFile.from_base64(encoded, filename="image.png")
        assert nf.content_type == "image/png"

    def test_explicit_content_type(self):
        encoded = base64.b64encode(b"data").decode("ascii")
        nf = NexusFile.from_base64(
            encoded, filename="data.bin", content_type="application/pdf"
        )
        assert nf.content_type == "application/pdf"

    def test_unknown_extension_fallback(self):
        encoded = base64.b64encode(b"data").decode("ascii")
        nf = NexusFile.from_base64(encoded, filename="file.xyz123")
        assert nf.content_type == "application/octet-stream"


class TestNexusFileReadWriteConsistency:
    """Tests that read() and aread() return identical data."""

    @pytest.mark.asyncio
    async def test_read_aread_consistency(self):
        data = b"consistent data across sync and async"
        nf = NexusFile(filename="test.dat", _data=data, size=len(data))
        sync_result = nf.read()
        async_result = await nf.aread()
        assert sync_result == async_result == data
