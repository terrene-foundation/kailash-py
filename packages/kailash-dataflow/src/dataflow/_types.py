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

from typing import Any, Protocol, runtime_checkable

__all__ = ["DataFlowProtocol"]


@runtime_checkable
class DataFlowProtocol(Protocol):
    """Structural shape of :class:`dataflow.core.engine.DataFlow` used by
    :mod:`dataflow.core.tenant_context`.

    The context switch binds (stores + re-exposes) a DataFlow instance and
    reads tenant configuration off ``config.security``. This Protocol captures
    exactly that surface — ``config`` — which the concrete
    :class:`dataflow.core.engine.DataFlow` exposes as a public instance
    attribute, so the concrete class satisfies the Protocol structurally.

    The earlier draft required ``multi_tenant`` / ``connection_manager`` /
    ``cache_backend`` as top-level attributes; the concrete class exposes
    those only privately (``_connection_manager``) or via ``config`` (the
    ``multi_tenant`` flag lives at ``config.security.multi_tenant``), so the
    over-specified Protocol made the concrete instance fail assignability.
    """

    config: Any
    """The :class:`DataFlowConfig` facade (carries ``security``, ``database``,
    cache settings, etc.)."""
