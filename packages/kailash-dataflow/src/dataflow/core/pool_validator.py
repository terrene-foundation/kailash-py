# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Startup pool configuration validator.

Validates that the configured connection pool will not exhaust the database
server's max_connections. Called once during DataFlow.connect() to catch
misconfigurations before the first query — not during a production outage.

Validation is advisory only: it logs ERROR/WARNING/INFO but does NOT prevent
startup. Some deployments (PgBouncer, intentional overcommit) are valid even
when the math looks dangerous.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from dataflow.core.pool_utils import (
    detect_worker_count,
    is_sqlite,
    probe_max_connections,
)

logger = logging.getLogger(__name__)

__all__ = ["validate_pool_config"]


def validate_pool_config(
    database_url: Optional[str],
    pool_size: int,
    max_overflow: int,
) -> Dict[str, Any]:
    """Validate pool configuration against database server limits.

    Args:
        database_url: Database connection URL.
        pool_size: Configured pool size per worker.
        max_overflow: Configured max overflow per worker.

    Returns:
        Dict with keys:
        - status: "safe" | "warning" | "error" | "skipped"
        - total_possible: total connections across all workers
        - db_max: server max_connections (or None)
        - workers: detected worker count
        - message: human-readable summary
    """
    # Defense-in-depth: clamp inputs to sane ranges
    pool_size = max(1, pool_size)
    max_overflow = max(0, max_overflow)

    # Skip for SQLite — no max_connections concept
    if not database_url or is_sqlite(database_url):
        return {
            "status": "skipped",
            "total_possible": 0,
            "db_max": None,
            "workers": 1,
            "message": "Validation skipped (SQLite or no URL)",
        }

    workers = detect_worker_count()
    total_possible = (pool_size + max_overflow) * workers

    # Probe database for max_connections
    db_max = probe_max_connections(database_url)

    if db_max is None:
        msg = (
            f"Could not validate pool config (probe failed). "
            f"Configured: pool_size={pool_size} + max_overflow={max_overflow} "
            f"x {workers} workers = {total_possible} connections"
        )
        logger.warning(msg)
        return {
            "status": "warning",
            "total_possible": total_possible,
            "db_max": None,
            "workers": workers,
            "message": msg,
        }

    safe_limit = int(db_max * 0.7)

    if total_possible > db_max:
        suggested = max(2, int(db_max * 0.7) // (workers * 3 // 2))
        msg = (
            f"CONNECTION POOL WILL EXHAUST: "
            f"pool_size={pool_size} + max_overflow={max_overflow} "
            f"x {workers} workers = {total_possible} connections, "
            f"but max_connections={db_max}. "
            f"Remediation: Set DATAFLOW_POOL_SIZE={suggested} "
            f"or reduce worker count."
        )
        logger.error(msg)
        return {
            "status": "error",
            "total_possible": total_possible,
            "db_max": db_max,
            "workers": workers,
            "message": msg,
        }

    if total_possible > safe_limit:
        pct = (total_possible / db_max) * 100
        msg = (
            f"CONNECTION POOL NEAR LIMIT: "
            f"pool_size={pool_size} + max_overflow={max_overflow} "
            f"x {workers} workers = {total_possible} connections "
            f"({pct:.0f}% of max_connections={db_max}). "
            f"Consider reducing pool_size or increasing max_connections."
        )
        logger.warning(msg)
        return {
            "status": "warning",
            "total_possible": total_possible,
            "db_max": db_max,
            "workers": workers,
            "message": msg,
        }

    pct = (total_possible / db_max) * 100
    msg = (
        f"Connection pool validated: {total_possible}/{db_max} "
        f"possible connections ({pct:.0f}% of limit)"
    )
    logger.info(msg)
    return {
        "status": "safe",
        "total_possible": total_possible,
        "db_max": db_max,
        "workers": workers,
        "message": msg,
    }
