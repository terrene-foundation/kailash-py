# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["NexusFile"]


@dataclass
class NexusFile:
    """Transport-agnostic file parameter.

    Normalizes file data across transport formats:
    - HTTP: multipart upload -> NexusFile.from_upload_file()
    - CLI: file path -> NexusFile.from_path()
    - MCP: base64 string -> NexusFile.from_base64()
    - WebSocket: binary frame -> NexusFile(data=bytes)

    Handlers receive NexusFile regardless of transport.
    """

    filename: str
    content_type: str = "application/octet-stream"
    size: int = 0
    _data: bytes = b""

    def read(self) -> bytes:
        """Read file contents synchronously."""
        return self._data

    async def aread(self) -> bytes:
        """Read file contents asynchronously."""
        return self._data

    @classmethod
    def from_upload_file(cls, upload_file) -> NexusFile:
        """Create from a FastAPI/Starlette UploadFile.

        Must be called from a sync context. In async context, read the
        file data first: ``data = await upload_file.read()`` then pass
        to NexusFile constructor.
        """
        data = upload_file.file.read()
        return cls(
            filename=upload_file.filename or "upload",
            content_type=upload_file.content_type or "application/octet-stream",
            size=len(data),
            _data=data,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> NexusFile:
        """Create from a local file path."""
        p = Path(path)
        data = p.read_bytes()
        content_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        return cls(
            filename=p.name,
            content_type=content_type,
            size=len(data),
            _data=data,
        )

    @classmethod
    def from_base64(
        cls, data: str, filename: str, content_type: Optional[str] = None
    ) -> NexusFile:
        """Create from base64-encoded data (MCP transport)."""
        decoded = base64.b64decode(data)
        ct = (
            content_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        return cls(
            filename=filename,
            content_type=ct,
            size=len(decoded),
            _data=decoded,
        )

    def to_dict(self) -> dict:
        """Serialize metadata (excludes binary data)."""
        return {
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
        }
