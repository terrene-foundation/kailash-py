# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Request-scoped ContextVars for Nexus ↔ downstream-engine propagation.

Per `specs/nexus-ml-integration.md` §§2–3, every request Nexus serves MUST
expose the authenticated tenant and actor to downstream engines (kailash-ml,
kailash-dataflow, kailash-kaizen) without the engine caller having to extract
JWT claims manually. These ``ContextVar`` s are the single propagation surface.

Wiring:
    - ``JWTMiddleware`` sets ``_current_tenant_id`` from the ``tenant_id`` JWT
      claim (OPTIONAL — ``None`` if absent) and ``_current_actor_id`` from the
      ``sub`` claim (MANDATORY per RFC 7519 §4.1.2) on every validated request.
    - Both are reset in a ``finally:`` block so a raised exception inside
      ``call_next`` cannot leak state into the next request on the same worker.

Standalone-vs-Nexus fallback chain:
    1. When ``kailash-nexus`` IS installed and an ambient JWT-authenticated
       request is active, downstream engines read these ContextVars and see
       the middleware-set values.
    2. When ``kailash-nexus`` is installed but no ambient request is running
       (e.g. a background job, a unit test, a notebook), the getters return
       ``None`` — downstream engines MUST handle the strict-mode multi-tenant
       error per `rules/tenant-isolation.md` §2.
    3. When ``kailash-nexus`` is NOT installed, downstream packages that want
       the propagation surface fall back to their own contextvars via a
       ``try/except ImportError`` compat layer (see
       `kailash_ml._compat.nexus_context`).

This module has no third-party dependencies; it is safe to import from any
code path that wants to read the ambient tenant/actor without taking a hard
dependency on FastAPI / Starlette / the JWT middleware.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

__all__ = [
    "_current_tenant_id",
    "_current_actor_id",
    "get_current_tenant_id",
    "set_current_tenant_id",
    "get_current_actor_id",
    "set_current_actor_id",
]


# Public underscore-prefixed names — the "underscore" signals these are
# process-wide ContextVar instances that production callers read/write via
# the getter/setter helpers below rather than touching the ContextVar handle
# directly. Tests that need to simulate a request scope MAY set them
# directly via ``set_current_tenant_id`` / ``set_current_actor_id``.
_current_tenant_id: ContextVar[Optional[str]] = ContextVar(
    "kailash_nexus.current_tenant_id",
    default=None,
)

_current_actor_id: ContextVar[Optional[str]] = ContextVar(
    "kailash_nexus.current_actor_id",
    default=None,
)


def get_current_tenant_id() -> Optional[str]:
    """Return the ambient tenant_id set by the JWT middleware.

    Returns ``None`` when no request scope is active OR when the request's
    JWT did not carry a ``tenant_id`` claim. Downstream engines that require
    a tenant_id under multi-tenant strict mode MUST raise a typed error
    (e.g. ``TenantRequiredError``) rather than silently default to a shared
    tenant — see `rules/tenant-isolation.md` §2.
    """
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: Optional[str]) -> Token[Optional[str]]:
    """Set the ambient tenant_id and return a ``Token`` for ``reset()``.

    The JWT middleware uses this on every validated request:

        token = set_current_tenant_id(payload.get("tenant_id"))
        try:
            response = await call_next(request)
        finally:
            _current_tenant_id.reset(token)

    Public for test code that simulates a request scope; production callers
    should go through ``JWTMiddleware`` which owns the reset-in-``finally``
    discipline. See `specs/nexus-ml-integration.md` §2.2 for the invariant.
    """
    return _current_tenant_id.set(tenant_id)


def get_current_actor_id() -> Optional[str]:
    """Return the ambient actor_id (JWT ``sub`` claim).

    Returns ``None`` when no request scope is active. ``sub`` is MANDATORY
    per RFC 7519 §4.1.2, so when a request IS active the value is always a
    non-empty string; the ``Optional[str]`` return is for the no-ambient-
    request path (background jobs, notebooks, unit tests).
    """
    return _current_actor_id.get()


def set_current_actor_id(actor_id: Optional[str]) -> Token[Optional[str]]:
    """Set the ambient actor_id and return a ``Token`` for ``reset()``.

    Symmetric to ``set_current_tenant_id`` — same reset-in-``finally``
    contract. See `specs/nexus-ml-integration.md` §3.
    """
    return _current_actor_id.set(actor_id)
