# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP channel adapter for ``InferenceServer``.

Per ``specs/ml-serving.md §1.1`` MCP is the third channel (alongside
REST and gRPC). The adapter exposes a single MCP tool ``predict_<model>``
and produces the canonical ``mcp+stdio://<handle>/predict_<model>``
URI shape. A short opaque ``handle`` segment lets operators distinguish
multiple servers in logs without leaking the full ``(tenant, version)``
tuple.

W25 ships the adapter in "handler callable" form. The actual MCP
transport is owned by ``kailash-mcp`` — W26+ mounts the handler as a
tool server; W25 returns the URI + callback only.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Mapping, Optional

from kailash_ml.serving.channels._base import ChannelBinding, InferenceCallback

__all__ = ["bind_mcp"]


logger = logging.getLogger(__name__)


def bind_mcp(
    *,
    model_name: str,
    model_version: int,
    invoke: InferenceCallback,
    server_id: str,
    tenant_id: Optional[str],
) -> ChannelBinding:
    """Bind the MCP channel.

    Parameters
    ----------
    model_name, model_version:
        Identify the exposed tool. The tool name is ``predict_<model>``.
    invoke:
        Async inference handler — ``InferenceServer`` wraps this with
        tenant-scope + signature validation before passing here.
    server_id:
        Opaque administrative identifier. Truncated to 12 hex chars for
        the URI handle segment so log aggregators can correlate across
        the ``server_id`` + ``handle`` prefix.
    tenant_id:
        Scope. Hashed into the handle so the URI does not leak the
        raw tenant id.

    Returns
    -------
    ChannelBinding
        ``channel="mcp"``, canonical URI, wrapped invoke, async stop.
    """
    if not model_name:
        raise ValueError("bind_mcp requires a non-empty model_name")

    # 12-hex handle segment is stable per (model, version, tenant) and
    # short enough that log aggregators can grep by prefix. Not load-
    # bearing for security — just a display identifier.
    handle_material = f"{server_id}:{model_name}:v{model_version}:{tenant_id}"
    handle = hashlib.sha256(handle_material.encode("utf-8")).hexdigest()[:12]
    uri = f"mcp+stdio://{handle}/predict_{model_name}"

    logger.info(
        "serving.channel.mcp.bind",
        extra={
            "channel": "mcp",
            "server_id": server_id,
            "tenant_id": tenant_id,
            "model": model_name,
            "model_version": model_version,
            "uri": uri,
            "handle": handle,
            "tool_name": f"predict_{model_name}",
            "mode": "real",
        },
    )

    async def _invoke(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return await invoke(payload)

    async def _stop() -> None:
        logger.info(
            "serving.channel.mcp.stop",
            extra={
                "channel": "mcp",
                "server_id": server_id,
                "tenant_id": tenant_id,
                "model": model_name,
                "model_version": model_version,
                "mode": "real",
            },
        )

    return ChannelBinding(
        channel="mcp",
        uri=uri,
        invoke=_invoke,
        stop=_stop,
        info={"handle": handle, "tool_name": f"predict_{model_name}"},
    )
