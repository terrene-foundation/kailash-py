# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Database URL resolution from environment variables.

Priority order:

* ``KAILASH_DATABASE_URL`` (Kailash-specific)
* ``DATABASE_URL`` (generic / Heroku-style)
* ``None`` (Level 0 — no database configured)

For queue URLs:

* ``KAILASH_QUEUE_URL``
* ``None`` (no queue configured)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "resolve_database_url",
    "resolve_queue_url",
]


def resolve_database_url() -> Optional[str]:
    """Resolve the database URL from environment variables.

    Checks in priority order:
    1. ``KAILASH_DATABASE_URL``
    2. ``DATABASE_URL``

    Returns ``None`` if neither is set or both are empty.
    """
    url = os.environ.get("KAILASH_DATABASE_URL", "") or os.environ.get(
        "DATABASE_URL", ""
    )
    if url:
        logger.debug("Resolved database URL (length=%d)", len(url))
        return url
    logger.debug("No database URL configured in environment")
    return None


def resolve_queue_url() -> Optional[str]:
    """Resolve the queue database URL from environment variables.

    Checks ``KAILASH_QUEUE_URL``.  Returns ``None`` if not set or empty.
    """
    url = os.environ.get("KAILASH_QUEUE_URL", "")
    if url:
        logger.debug("Resolved queue URL (length=%d)", len(url))
        return url
    logger.debug("No queue URL configured in environment")
    return None
