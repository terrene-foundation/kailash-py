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

import contextlib
import contextvars
from typing import Any, Callable, Iterator, Optional

from ..exceptions import DataFlowConnectionError

__all__ = [
    "build_asyncpg_credential_connect",
    "open_credentialed_connection",
    "get_active_credential_provider",
    "credential_provider_scope",
]

# Issue #1741: a context-scoped fallback source for the per-connection
# credential callback, used by connection sites that build their asyncpg
# connection from serializable params only and hold NO reference to the
# DataFlow instance/config (the standalone WorkflowBuilder bulk nodes
# ``BulkCreatePoolNode`` / ``DataFlowBulkUpsertNode`` — a live ``Callable``
# cannot ride the workflow-parameter channel). The Kailash runtime snapshots
# ``contextvars.copy_context()`` at every thread-boundary dispatch and runs the
# node inside it, so a provider bound before ``runtime.execute(...)`` is visible
# inside the node's ``async_run``. The db.express / db.transactions / db.bulk_*
# CRUD path does NOT use this — it threads the provider explicitly through
# ``_get_or_create_async_sql_node``.
_active_credential_provider: contextvars.ContextVar[Optional[Callable[[], str]]] = (
    contextvars.ContextVar("dataflow_active_credential_provider", default=None)
)


def get_active_credential_provider() -> Optional[Callable[[], str]]:
    """Return the context-bound credential provider, or None if unbound."""
    return _active_credential_provider.get()


@contextlib.contextmanager
def credential_provider_scope(
    credential_provider: Optional[Callable[[], str]],
) -> Iterator[None]:
    """Bind ``credential_provider`` for the current context (and any task /
    thread-boundary dispatch descended from it) for the duration of the block.

    Use this to give token-based DB auth (Azure AD / AWS IAM) to the standalone
    ``BulkCreatePoolNode`` / ``DataFlowBulkUpsertNode`` workflow nodes, which
    take only a serializable ``connection_string`` and cannot accept a live
    callback as a node parameter::

        with credential_provider_scope(provide_token):
            runtime.execute(workflow.build())

    The token/reset is scoped (``ContextVar.reset``) so it never leaks across
    instances or tests. None is a no-op (behavior unchanged).
    """
    token = _active_credential_provider.set(credential_provider)
    try:
        yield
    finally:
        _active_credential_provider.reset(token)


async def open_credentialed_connection(
    asyncpg_module: Any,
    *args: Any,
    credential_provider: Optional[Callable[[], str]] = None,
    context: str = "PostgreSQL",
    **connect_kwargs: Any,
):
    """Open a SINGLE asyncpg connection, minting a FRESH credential via
    ``credential_provider`` (issue #1741) when set — else a plain
    ``asyncpg.connect`` (behavior unchanged).

    The single shared entry point for every non-pool single-connection site
    (the sync-transaction path, the staging probe / maintenance-DB admin
    connects, and the engine DDL / verify / migration connects), so the
    fail-closed + no-secret-in-logs contract lives in exactly one place. The
    minted token overrides any ``password`` embedded in a positional DSN or
    passed as a ``password=`` kwarg (asyncpg's explicit kwarg wins), so tokens
    containing ``&=/%`` need no percent-encoding.
    """
    if credential_provider is not None:
        connect = build_asyncpg_credential_connect(
            credential_provider, asyncpg_module, context=context
        )
        return await connect(*args, **connect_kwargs)
    return await asyncpg_module.connect(*args, **connect_kwargs)


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
            # name is safe to surface. Use ``from None`` (NOT ``from exc``):
            # ``from exc`` would re-attach the token-bearing provider
            # exception as ``__cause__``, so it renders in full under any
            # upstream ``logger.exception(...)`` / traceback — defeating the
            # str(exc)-stripping above. ``from None`` severs the chain at the
            # single shared source, covering every consuming pool
            # (adapter / lightweight / event-store) at once
            # (security.md "No secrets in logs").
            raise DataFlowConnectionError(
                f"credential_provider() raised while establishing a new "
                f"{context} physical connection ({type(exc).__name__}); "
                "refusing to fall back to a stale or absent credential"
            ) from None

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
