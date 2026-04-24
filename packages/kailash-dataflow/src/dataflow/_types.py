# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared types for :mod:`dataflow`.

Breaks the static import cycle between
:mod:`dataflow.core.tenant_context`, :mod:`dataflow.core.engine`, and
:mod:`dataflow.features.express`:

* ``engine`` imports ``ExpressDataFlow`` / ``SyncExpress`` from
  ``features.express`` at module scope.
* ``features.express`` imports ``get_current_tenant_id`` from
  ``core.tenant_context`` at module scope.
* ``core.tenant_context`` imports ``DataFlow`` from ``core.engine``
  under ``TYPE_CHECKING`` — the cycle's back-edge.

This leaf module exposes :class:`DataFlowProtocol` — a
structural Protocol that captures the minimum surface
``core.tenant_context`` needs from a ``DataFlow`` instance. The
concrete :class:`dataflow.core.engine.DataFlow` satisfies the
Protocol at runtime because Python's structural type checking is
duck-typed on attribute presence.

``tenant_context`` now imports ``DataFlowProtocol`` eagerly from here —
no more TYPE_CHECKING back-edge.

The helper :func:`get_current_tenant_id` is re-exported so downstream
callers can import it from either :mod:`dataflow.core.tenant_context`
(original) or :mod:`dataflow._types` (cycle-aware). This is the only
runtime-surface export the leaf module owns.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

__all__ = ["DataFlowProtocol"]


@runtime_checkable
class DataFlowProtocol(Protocol):
    """Structural shape of :class:`dataflow.core.engine.DataFlow` used by
    :mod:`dataflow.core.tenant_context`.

    The context switch only observes the facade surfaces a tenant-aware
    operation needs — the connection manager, the optional cache backend,
    and the ``multi_tenant`` configuration flag. The concrete
    :class:`DataFlow` class exposes a much wider API; this Protocol
    captures only what the context switch actually reads.
    """

    multi_tenant: bool
    """Whether the bound instance runs in multi-tenant mode."""

    connection_manager: Any
    """The SQL connection pool facade (:class:`ConnectionManager` or
    equivalent)."""

    cache_backend: Optional[Any]
    """Optional cache adapter (None when cache is disabled)."""
