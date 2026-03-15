# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Platform-agnostic resource path normalization for constraint patterns.

All constraint patterns and resource paths stored in trust-plane records
use forward slashes, regardless of platform. This module provides the
single normalization function used throughout the codebase.

This is a **pure function** -- no filesystem access, no I/O, no side effects.
It operates entirely on string content.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["normalize_resource_path"]


def normalize_resource_path(path: str | Path) -> str:
    """Normalize a resource path to use forward slashes consistently.

    Converts any path representation to a canonical forward-slash form
    suitable for constraint pattern storage and comparison.

    Behavior:
    - Converts backslashes to forward slashes
    - Removes trailing slashes (except bare ``/``)
    - Collapses double slashes (except leading ``//`` for UNC paths)
    - Does NOT resolve ``.`` or ``..`` segments (pure string transform)
    - Does NOT access the filesystem

    Args:
        path: A string or Path-like object to normalize.

    Returns:
        Normalized path string with forward slashes.
    """
    result = str(path)

    if not result:
        return ""

    # Step 1: Convert all backslashes to forward slashes
    result = result.replace("\\", "/")

    # Step 2: Detect and preserve UNC prefix (leading //)
    unc_prefix = ""
    if result.startswith("//"):
        unc_prefix = "//"
        result = result[2:]

    # Step 3: Collapse all runs of multiple slashes to a single slash
    result = re.sub(r"/{2,}", "/", result)

    # Step 4: Restore UNC prefix if present
    result = unc_prefix + result

    # Step 5: Remove trailing slashes, but preserve bare "/"
    if result != "/" and len(result) > 1:
        result = result.rstrip("/")

    return result
