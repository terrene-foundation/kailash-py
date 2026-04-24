# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared types for serving channel adapters.

Each ``ChannelBinding`` captures:

* ``channel`` — which transport (``"rest"``, ``"mcp"``, ``"grpc"``).
* ``uri`` — the canonical URI the channel advertises.
* ``invoke`` — the async callback that runs inference for one request.
* ``stop`` — the async callback that releases channel resources.

Per ``rules/framework-first.md`` the channel layer MUST NOT reinvent
HTTP routing — the REST adapter constructs the URI shape + handler
callback; the actual HTTP mount is left to ``kailash-nexus`` (which
serves REST, MCP, CLI under one ``Nexus()`` app). The MCP adapter
likewise constructs the ``mcp+stdio://`` URI form and the tool callback;
the actual transport is ``kailash-mcp``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional

__all__ = [
    "ChannelBinding",
    "InferenceCallback",
    "ShutdownCallback",
]


# Async callback signatures --------------------------------------------------
InferenceCallback = Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]]
"""Signature of the channel invoke handler.

``InferenceServer`` wraps the model predict path and passes a closure
that implements this signature. The tenant scope check + signature
validation + observability log points live inside the server's wrapper
(NOT inside the channel adapter), so every channel benefits from the
same audit trail.
"""


ShutdownCallback = Callable[[], Awaitable[None]]
"""Signature of the channel shutdown handler — releases resources."""


@dataclass(frozen=False, slots=True)
class ChannelBinding:
    """Record of one channel bind produced by an adapter.

    :attr:`channel` is the transport name used as the key in
    :attr:`ServeHandle.urls` and in the structured log lines. :attr:`uri`
    is the externally-advertised URI form. :attr:`invoke` is the async
    entry point; the caller passes the normalised payload and receives
    the prediction mapping. :attr:`stop` is called exactly once by
    :meth:`InferenceServer.stop`.
    """

    channel: str
    uri: str
    invoke: InferenceCallback
    stop: ShutdownCallback
    # Optional per-channel diagnostics (e.g. the gRPC port actually
    # bound). Opaque mapping — adapter-specific shape.
    info: Optional[Mapping[str, Any]] = None
