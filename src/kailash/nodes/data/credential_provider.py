# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Shared per-physical-connection credential-callback wrapper for core asyncpg pools.

Issue #1741 (follow-up to #1737): token-based DB auth (Azure AD / AWS IAM)
requires a FRESH credential to be minted for EVERY physical connection an
asyncpg pool opens (initial fill, recycle, overflow, reconnect) — not the
connection string captured once at pool-construction time.

This is the CORE-SDK sibling of ``dataflow.core.credential_provider``. The
core ``AsyncSQLDatabaseNode`` pool (``kailash.nodes.data.async_sql``) is the
pool the ``db.express`` / ``db.transactions`` / bulk CRUD hot path actually
opens — the three pools wired in #1737 live in the DataFlow package and cover
only the probe / health-check / audit-trail connections. The core SDK cannot
import the DataFlow helper (the dependency direction is DataFlow → core, never
the reverse), so the identical fail-closed contract lives here, in exactly one
core-side place, and every core asyncpg pool that wants this behavior builds
its ``connect=`` override through :func:`build_asyncpg_credential_connect`.

See ``DatabaseConfig.credential_provider`` (``kailash/nodes/data/async_sql.py``)
for the field contract, and the DataFlow helper for the sibling package.
"""

from __future__ import annotations

from typing import Any, Callable

from kailash.sdk_exceptions import NodeExecutionError

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
    ``max_inactive_connection_lifetime``, on overflow up to ``max_size``, and
    on reconnect after a holder's connection dies. Overriding ``connect``
    (rather than baking a static password into ``connect_kwargs`` once) is the
    asyncpg-native equivalent of SQLAlchemy's ``do_connect`` event — the
    callback fires per physical connection, satisfying #1737's "EVERY physical
    connection" acceptance criterion with a stricter guarantee than an
    interval-based refresh-ahead approach (zero staleness window).

    Fail-closed: a raising (or non-str-returning) ``credential_provider``
    raises ``NodeExecutionError`` here — it NEVER falls back to the static
    ``password`` captured in ``connect_kwargs`` at pool-construction time. The
    minted token is set as the driver PARAM (``connect_kwargs["password"]``),
    never re-encoded into a DSN/URL, so tokens containing ``&``, ``=``, ``/``,
    ``%`` (AWS IAM tokens) need no percent-encoding — asyncpg's explicit
    ``password=`` kwarg overrides the password embedded in a positional DSN.
    The token is NEVER logged (not the value, not its length, not a prefix)
    and is held locally only for the duration of the connect call.

    Args:
        credential_provider: Zero-arg callable returning a fresh password/
            token. MUST return a non-empty ``str``.
        asyncpg_module: The ``asyncpg`` module (or a Protocol-satisfying
            stand-in for it in tests) whose ``connect()`` is delegated to.
        context: Human-readable pool identity used ONLY in the fail-closed
            error message (e.g. ``"PostgreSQL"``) — never includes secret
            material.
    """
    provider = credential_provider

    async def _connect_with_fresh_credential(*args: Any, **connect_kwargs: Any):
        try:
            token = provider()
        except Exception as exc:
            # Do NOT interpolate str(exc) — a provider's exception message
            # could echo back token material. Only the exception's type name
            # is safe to surface. Use ``from None`` (NOT ``from exc``):
            # ``from exc`` would re-attach the token-bearing provider exception
            # as ``__cause__``, so it renders in full under any upstream
            # ``logger.exception(...)`` / traceback — defeating the
            # str(exc)-stripping above. ``from None`` severs the chain at the
            # single shared source (security.md "No secrets in logs").
            raise NodeExecutionError(
                f"credential_provider() raised while establishing a new "
                f"{context} physical connection ({type(exc).__name__}); "
                "refusing to fall back to a stale or absent credential"
            ) from None

        if not isinstance(token, str) or not token:
            raise NodeExecutionError(
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
