# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Channel adapters for ``InferenceServer``.

Each adapter produces a :class:`ChannelBinding` with a canonical URI and
two async callbacks — ``invoke(payload, *, tenant_id)`` and ``stop()``.
``InferenceServer`` composes these into a multi-channel serving lifecycle.

Per ``specs/ml-serving.md §1.2`` (What InferenceServer IS NOT) —
channel adapters MUST NOT own their own HTTP routing primitives; REST
mounts through ``kailash-nexus`` and MCP through ``kailash-mcp``.
gRPC sits behind the ``[grpc]`` optional extra per W25 invariant 8.
"""
from __future__ import annotations

from kailash_ml.serving.channels._base import (
    ChannelBinding,
    InferenceCallback,
    ShutdownCallback,
)

__all__ = [
    "ChannelBinding",
    "InferenceCallback",
    "ShutdownCallback",
    "bind_rest",
    "bind_mcp",
    "bind_grpc",
]


def bind_rest(*args, **kwargs):  # pragma: no cover - thin re-export
    """Bind the REST channel — see :mod:`kailash_ml.serving.channels.rest`."""
    from kailash_ml.serving.channels.rest import bind_rest as _bind

    return _bind(*args, **kwargs)


def bind_mcp(*args, **kwargs):  # pragma: no cover - thin re-export
    """Bind the MCP channel — see :mod:`kailash_ml.serving.channels.mcp`."""
    from kailash_ml.serving.channels.mcp import bind_mcp as _bind

    return _bind(*args, **kwargs)


def bind_grpc(*args, **kwargs):  # pragma: no cover - thin re-export
    """Bind the gRPC channel — see :mod:`kailash_ml.serving.channels.grpc`."""
    from kailash_ml.serving.channels.grpc import bind_grpc as _bind

    return _bind(*args, **kwargs)
