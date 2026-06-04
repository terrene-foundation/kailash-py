"""Typed exceptions for the Kailash data nodes (issue #697 + #698).

Centralizes the small typed-error surface that the connection-lifecycle
fix introduces. Sits beside ``kailash.sdk_exceptions`` (the SDK-wide
hierarchy) and re-uses ``NodeExecutionError`` as the parent so existing
``except NodeExecutionError`` callers keep working.

See also:
    - ``rules/zero-tolerance.md`` Rule 3 — silent fallbacks BLOCKED;
      ``PoolExhaustedError`` is the typed surface that turns the
      previously-silent ``Exception: continue`` fallback in
      ``AsyncSQLDatabaseNode._get_adapter`` into a loud, actionable
      error with an override hint.
    - ``rules/dataflow-pool.md`` Rule 5 — orphan-pool defense; the
      registry cap that this exception enforces is the structural fix.
    - ``specs/dataflow-cache.md`` § Pool Lifecycle Contract.
"""

from __future__ import annotations

from kailash.sdk_exceptions import NodeExecutionError
from kailash.utils.url_credentials import redact_pool_key

__all__ = ["PoolExhaustedError"]


class PoolExhaustedError(NodeExecutionError):
    """Raised when ``AsyncSQLDatabaseNode`` would exceed the per-process pool cap.

    The ``EnterpriseConnectionPool`` fallback path (``_get_adapter``) used
    to silently create a new dedicated 5-20 connection pool every time
    the per-pool lock timed out, with no process-wide bound. Under
    saturation that produced the JourneyMate / Azure PostgreSQL
    connection-leak class — 480-500 backend connections vs the 100-200
    server ceiling.

    The fix bounds total pool count at
    ``_POOL_DEFAULTS["max_pool_count_per_process"]`` (default 100). When
    the cap is reached this exception is raised in place of the silent
    fallback. The error message names ``set_pool_defaults()`` so the
    operator has a single place to either raise the cap or reduce
    contention pressure (lower lock timeout, fix root cause).

    Args:
        current: Pool count observed at the time of refusal. Equals
            ``len(_PROCESS_POOL_REGISTRY)`` at the call site.
        cap: Configured maximum from
            ``_POOL_DEFAULTS["max_pool_count_per_process"]``.
        pool_key: The pool key that would have been created. Useful
            for forensic correlation in incident logs (mirrors the
            ``pool_key`` log field emitted by the WARN logger on
            successful fallback).

    Attributes:
        current (int): Observed pool count.
        cap (int): Configured cap.
        pool_key (str): Pool key the caller was attempting to create.

    Example:
        >>> try:
        ...     await db.express.list("User")
        ... except PoolExhaustedError as e:
        ...     # Operator sees: "Pool count 100 exceeds cap 100; ..."
        ...     # → either raise the cap via set_pool_defaults(...)
        ...     # → or fix the contention root cause (lock timeout, etc.)
        ...     raise
    """

    def __init__(self, current: int, cap: int, pool_key: str) -> None:
        if not isinstance(current, int) or current < 0:
            raise ValueError(f"current must be a non-negative int (got {current!r})")
        if not isinstance(cap, int) or cap < 1:
            raise ValueError(f"cap must be a positive int (got {cap!r})")
        if not isinstance(pool_key, str):
            raise ValueError(
                f"pool_key must be a string (got {type(pool_key).__name__})"
            )

        self.current: int = current
        self.cap: int = cap
        # Redact the connection-string segment: the pool key can carry
        # credentials (``postgresql://user:pass@host/db``) and this error
        # message propagates to logs / aggregators on the disposal path
        # (issue #1260). Redaction is deterministic, so the value still
        # serves the forensic-correlation purpose the attribute documents.
        self.pool_key: str = redact_pool_key(pool_key)
        message = (
            f"Pool count {current} exceeds cap {cap}; "
            f"refusing to create dedicated fallback pool. "
            f"Override via "
            f"set_pool_defaults(max_pool_count_per_process=N) "
            f"or fix the contention root cause "
            f"(per-pool lock timeout, DDL retry storm, etc.). "
            f"pool_key={self.pool_key!r}"
        )
        super().__init__(message)
