"""Convenience loaders for manifest files.

Validates the file extension before delegating to the appropriate
manifest class.

SECURITY — path handling
-------------------------
``load_manifest`` / ``load_app_manifest`` open the ``path`` they are
handed after only a ``.toml`` suffix check; they apply NO path-traversal,
symlink, or allowlist containment guard. This is safe today because NO
caller passes an externally-influenced path: the MCP catalog server's
``deploy_agent`` tool takes inline TOML content (and explicitly rejects
anything that looks like a file path, RT-06), and never imports this
module. Any FUTURE caller that passes a ``path`` derived from untrusted
input (an HTTP request, an MCP argument, a manifest field) MUST FIRST
resolve the path and confirm it stays within an approved base directory
(e.g. ``Path(base).resolve() in Path(path).resolve().parents``) or match
it against an allowlist — otherwise ``../../etc/secrets.toml`` and symlink
escapes become readable. Do not add such a caller without that guard.
"""

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

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

    Security:
        *path* is opened after only a suffix check — no traversal /
        allowlist containment guard is applied. A caller passing an
        externally-influenced *path* MUST apply a containment or allowlist
        check first (see the module docstring).
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

    Security:
        *path* is opened after only a suffix check — no traversal /
        allowlist containment guard is applied. A caller passing an
        externally-influenced *path* MUST apply a containment or allowlist
        check first (see the module docstring).
    """
    if not path.endswith(".toml"):
        raise ManifestParseError(
            f"Expected .toml file, got: {path}",
            details={"path": path},
        )
    return AppManifest.from_toml(path)
