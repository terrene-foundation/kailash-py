# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Shared per-physical-connection credential-callback wrapper for asyncpg pools.

Issue #1737: token-based DB auth (Azure AD / AWS IAM) requires a FRESH
credential to be minted for EVERY physical connection an asyncpg pool opens
(initial fill, recycle, overflow, reconnect) — not the connection string
captured once at pool-construction time. Every DataFlow-package asyncpg pool
that wants this behavior (``dataflow.adapters.postgresql.PostgreSQLAdapter``,
``dataflow.core.pool_lightweight.LightweightPool``,
``dataflow.core.event_stores.postgresql.PostgreSQLEventStore``) builds its
``connect=`` override through :func:`build_asyncpg_credential_connect` so the
fail-closed contract and no-secret-in-logs guarantee live in exactly one
place.

See ``DatabaseConfig.credential_provider`` (``dataflow/core/config.py``) for
the full field contract.
"""

from __future__ import annotations

from typing import Any, Callable

from ..exceptions import DataFlowConnectionError

__all__ = ["build_asyncpg_credential_connect"]


def build_asyncpg_credential_connect(
    credential_provider: Callable[[], str],
    asyncpg_module: Any,
    *,
    context: str = "PostgreSQL",
) -> Callable:
    """Build an asyncpg ``connect`` callable that mints a fresh credential.

    asyncpg's ``Pool`` invokes ``self._connect(*connect_args, **connect_kwargs)``
    (defaulting to ``asyncpg.connect``) every time it needs a NEW physical
    connection — on initial pool fill, on recycle after
    ``max_inactive_connection_lifetime``, on overflow up to ``max_size``,
    and on reconnect after a holder's connection dies (including after
    ``Pool.expire_connections()``). Overriding ``connect`` (rather than
    baking a static password into ``connect_kwargs`` once) is the
    asyncpg-native equivalent of SQLAlchemy's ``do_connect`` event — the
    callback fires per physical connection, satisfying #1737's "EVERY
    physical connection" acceptance criterion with a stricter guarantee
    than an interval-based refresh-ahead approach (zero staleness window).

    Fail-closed: a raising (or non-str-returning) ``credential_provider``
    raises ``DataFlowConnectionError`` here — it NEVER falls back to the
    static ``password`` captured in ``connect_kwargs`` at pool-construction
    time. The minted token is set as the driver PARAM (``connect_kwargs
    ["password"]``), never re-encoded into a DSN/URL, so tokens containing
    ``&``, ``=``, ``/``, ``%`` (AWS IAM tokens) need no percent-encoding.
    The token is NEVER logged (not the value, not its length, not a
    prefix) and is held locally only for the duration of the connect call.

    Args:
        credential_provider: Zero-arg callable returning a fresh password/
            token. MUST return a non-empty ``str``.
        asyncpg_module: The ``asyncpg`` module (or a Protocol-satisfying
            stand-in for it in tests) whose ``connect()`` is delegated to.
        context: Human-readable pool identity used ONLY in the fail-closed
            error message (e.g. ``"PostgreSQL"``,
            ``"PostgreSQL lightweight pool"``,
            ``"PostgreSQL event store"``) — never includes secret material.
    """
    provider = credential_provider

    async def _connect_with_fresh_credential(*args: Any, **connect_kwargs: Any):
        try:
            token = provider()
        except Exception as exc:
            # Do NOT interpolate str(exc) — a provider's exception message
            # could echo back token material. Only the exception's type
            # name is safe to surface.
            raise DataFlowConnectionError(
                f"credential_provider() raised while establishing a new "
                f"{context} physical connection ({type(exc).__name__}); "
                "refusing to fall back to a stale or absent credential"
            ) from exc

        if not isinstance(token, str) or not token:
            raise DataFlowConnectionError(
                "credential_provider() must return a non-empty str; got "
                f"{type(token).__name__}"
            )

        connect_kwargs["password"] = token
        try:
            return await asyncpg_module.connect(*args, **connect_kwargs)
        finally:
            # Hold the live secret as briefly as possible: drop the local
            # binding as soon as it has been handed to the driver.
            token = None
            connect_kwargs["password"] = None

    return _connect_with_fresh_credential
