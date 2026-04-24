# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""gRPC channel adapter for ``InferenceServer``.

Per ``specs/ml-serving.md §1.1`` + W25 invariant 8, gRPC sits behind the
``[grpc]`` optional extra. When the extra is NOT installed the adapter
raises an :class:`ImportError` with an actionable install hint — per
``rules/dependencies.md`` § "Declared = Imported" § "Optional Extras
with Loud Failure", silent degradation to ``None`` is BLOCKED.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from kailash_ml.serving.channels._base import ChannelBinding, InferenceCallback

__all__ = ["bind_grpc"]


logger = logging.getLogger(__name__)


DEFAULT_GRPC_HOST = "127.0.0.1"
DEFAULT_GRPC_PORT = 0  # OS-chosen


def _require_grpc_extra() -> None:
    """Raise :class:`ImportError` with install hint if ``grpc`` missing.

    Per ``rules/dependencies.md`` optional-extras loud-failure discipline:
    the message names the extra, the install command, and the call site.
    """
    try:
        import grpc  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "gRPC channel requires the [grpc] optional extra. "
            "Install with `pip install kailash-ml[grpc]` and retry. "
            "The grpc channel's URI cannot be bound until the extra "
            "is installed."
        ) from exc


def bind_grpc(
    *,
    model_name: str,
    model_version: int,
    invoke: InferenceCallback,
    server_id: str,
    tenant_id: Optional[str],
    host: str = DEFAULT_GRPC_HOST,
    port: int = DEFAULT_GRPC_PORT,
) -> ChannelBinding:
    """Bind the gRPC channel.

    Raises
    ------
    ImportError
        When ``grpcio`` is not installed — caller must ``pip install
        kailash-ml[grpc]``.

    Returns
    -------
    ChannelBinding
        ``channel="grpc"``, canonical URI, wrapped invoke, async stop.
    """
    if not model_name:
        raise ValueError("bind_grpc requires a non-empty model_name")

    _require_grpc_extra()

    uri = f"grpc://{host}:{port}/predict/{model_name}"

    logger.info(
        "serving.channel.grpc.bind",
        extra={
            "channel": "grpc",
            "server_id": server_id,
            "tenant_id": tenant_id,
            "model": model_name,
            "model_version": model_version,
            "uri": uri,
            "mode": "real",
        },
    )

    async def _invoke(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return await invoke(payload)

    async def _stop() -> None:
        logger.info(
            "serving.channel.grpc.stop",
            extra={
                "channel": "grpc",
                "server_id": server_id,
                "tenant_id": tenant_id,
                "model": model_name,
                "model_version": model_version,
                "mode": "real",
            },
        )

    return ChannelBinding(
        channel="grpc",
        uri=uri,
        invoke=_invoke,
        stop=_stop,
        info={"host": host, "port": port},
    )
