from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kaizen Manifest Models — declarative agent and application manifests.

Provides :class:`AgentManifest`, :class:`AppManifest`, and
:class:`GovernanceManifest` as ``@dataclass`` models with TOML parsing,
dict round-trip serialization, and A2A Agent Card conversion.
"""

from kaizen.manifest.agent import AgentManifest
from kaizen.manifest.app import AppManifest
from kaizen.manifest.errors import (
    ManifestError,
    ManifestParseError,
    ManifestValidationError,
)
from kaizen.manifest.governance import GovernanceManifest

__all__ = [
    "AgentManifest",
    "AppManifest",
    "GovernanceManifest",
    "ManifestError",
    "ManifestParseError",
    "ManifestValidationError",
]
