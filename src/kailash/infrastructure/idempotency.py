# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Execution-level idempotency for workflow runs.

Wraps any runtime's execute method to provide exactly-once semantics
using the DBIdempotencyStore.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["IdempotentExecutor"]


class IdempotentExecutor:
    """Wraps workflow execution with idempotency guarantees.

    Before executing a workflow, checks if the idempotency key has already
    been used. If so, returns the cached result. If not, claims the key,
    executes, and stores the result atomically.

    On execution failure, the claim is released so the key can be retried.

    Parameters
    ----------
    idempotency_store:
        A :class:`~kailash.infrastructure.idempotency_store.DBIdempotencyStore`
        (or compatible) instance.
    ttl_seconds:
        How long to cache results (default: 1 hour).
    """

    def __init__(self, idempotency_store: Any, ttl_seconds: int = 3600):
        self._store = idempotency_store
        self._ttl = ttl_seconds

    async def execute(
        self,
        runtime: Any,
        workflow: Any,
        parameters: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Execute a workflow with idempotency.

        If *idempotency_key* is ``None``, executes without dedup (pass-through).

        Returns
        -------
        tuple[dict, str]
            ``(results, run_id)`` — same as ``runtime.execute()``.
        """
        if idempotency_key is None:
            return runtime.execute(workflow, parameters=parameters or {})

        # 1. Check for cached result
        cached = await self._store.get(idempotency_key)
        if cached is not None:
            logger.info("Idempotent hit: key=%s", idempotency_key)
            cached_data = json.loads(cached["response_data"])
            return cached_data.get("results", {}), cached_data.get("run_id", "")

        # 2. Claim the key
        fingerprint = idempotency_key
        claimed = await self._store.try_claim(idempotency_key, fingerprint)
        if not claimed:
            # Another worker claimed — check if result available
            cached = await self._store.get(idempotency_key)
            if cached is not None:
                cached_data = json.loads(cached["response_data"])
                return cached_data.get("results", {}), cached_data.get("run_id", "")
            raise RuntimeError(
                f"Idempotency key '{idempotency_key}' is claimed by another worker "
                f"but no result is available yet"
            )

        # 3. Execute
        try:
            results, run_id = runtime.execute(workflow, parameters=parameters or {})
        except Exception:
            await self._store.release_claim(idempotency_key)
            raise

        # 4. Store result — pass the dict; store_result handles JSON encoding
        result_payload = {"results": results, "run_id": run_id}
        await self._store.store_result(
            idempotency_key, result_payload, status_code=200, headers={}
        )

        logger.info("Idempotent execute: key=%s run_id=%s", idempotency_key, run_id)
        return results, run_id
