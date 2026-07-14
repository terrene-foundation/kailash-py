from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Convenience loaders for manifest files.

Validates the file extension before delegating to the appropriate
manifest class.
"""

import logging

from kaizen.manifest.agent import AgentManifest
from kaizen.manifest.app import AppManifest
from kaizen.manifest.errors import ManifestParseError

logger = logging.getLogger(__name__)

__all__ = ["load_manifest", "load_app_manifest"]


def load_manifest(path: str) -> AgentManifest:
    """Load an AgentManifest from a TOML file.

    Args:
        path: Filesystem path to the ``.toml`` manifest.

    Returns:
        Parsed :class:`AgentManifest`.

    Raises:
        ManifestParseError: If *path* does not end with ``.toml`` or
            the file cannot be read/parsed.
    """
    if not path.endswith(".toml"):
        raise ManifestParseError(
            f"Expected .toml file, got: {path}",
            details={"path": path},
        )
    return AgentManifest.from_toml(path)


def load_app_manifest(path: str) -> AppManifest:
    """Load an AppManifest from a TOML file.

    Args:
        path: Filesystem path to the ``.toml`` manifest.

    Returns:
        Parsed :class:`AppManifest`.

    Raises:
        ManifestParseError: If *path* does not end with ``.toml`` or
            the file cannot be read/parsed.
    """
    if not path.endswith(".toml"):
        raise ManifestParseError(
            f"Expected .toml file, got: {path}",
            details={"path": path},
        )
    return AppManifest.from_toml(path)
