# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""REST channel adapter for ``InferenceServer``.

Per ``specs/ml-serving.md §5.1`` REST is the primary (default) channel
and MUST satisfy:

* W25 invariant 3 — ``urls["rest"].endswith("/predict/{ModelName}")``.
* W25 invariant 4 — ``GET /health → 200`` when the model is registered.
* ``rules/framework-first.md`` — raw HTTP frameworks are BLOCKED; the
  REST adapter produces a URI + async handler, and the actual HTTP
  server is ``kailash-nexus``.

W25 ships the adapter in "in-process handler" form: the URI advertises
a canonical ``http://<host>:<port>/predict/<ModelName>`` shape; the
handler is an async callable that ``InferenceServer`` wraps with
tenant-scope checking, signature validation, and observability. When a
Nexus ``app`` is passed in later waves (W26+) the adapter mounts the
handler onto the app; W25 produces the handler callable only.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from kailash_ml.serving.channels._base import ChannelBinding, InferenceCallback

__all__ = [
    "bind_rest",
    "DEFAULT_REST_HOST",
    "DEFAULT_REST_PORT",
]


logger = logging.getLogger(__name__)


DEFAULT_REST_HOST = "127.0.0.1"
"""Bind host for the REST channel when no Nexus app is supplied."""

DEFAULT_REST_PORT = 0
"""Bind port 0 means "let the OS choose" — canonical URI includes :0."""


def bind_rest(
    *,
    model_name: str,
    model_version: int,
    invoke: InferenceCallback,
    host: str = DEFAULT_REST_HOST,
    port: int = DEFAULT_REST_PORT,
    server_id: str,
    tenant_id: Optional[str],
) -> ChannelBinding:
    """Bind the REST channel.

    The canonical URI shape is ``http://<host>:<port>/predict/<model>``
    per W25 invariant 3 (``urls["rest"].endswith("/predict/ModelName")``).

    Parameters
    ----------
    model_name:
        Model name. Appears verbatim at the end of the URI — the test
        ``urls["rest"].endswith(f"/predict/{model_name}")`` MUST pass.
    model_version:
        Version integer; not in the URI for REST (per spec the alias /
        version pin is resolved at construction and reflected only in
        log lines + the ``ServeHandle.model_version`` field).
    invoke:
        The inference-handler callback. ``InferenceServer`` passes the
        wrapped-for-tenant-scope+signature-validation closure.
    host, port:
        URI host/port. Default ``127.0.0.1:0`` — OS-chosen port. In-
        process tests round-trip by invoking ``binding.invoke(payload)``
        directly; the URI is a display contract.
    server_id:
        Opaque identifier used in structured log lines.
    tenant_id:
        Scopes the binding; emitted on every log line.

    Returns
    -------
    ChannelBinding
        ``channel="rest"``, canonical URI, wrapped invoke, no-op stop.
    """
    if not model_name:
        raise ValueError("bind_rest requires a non-empty model_name")

    # Canonical URI — W25 invariant 3 strictly requires the trailing
    # "/predict/{ModelName}" form. "endswith" asserts this shape.
    uri = f"http://{host}:{port}/predict/{model_name}"

    logger.info(
        "serving.channel.rest.bind",
        extra={
            "channel": "rest",
            "server_id": server_id,
            "tenant_id": tenant_id,
            "model": model_name,
            "model_version": model_version,
            "uri": uri,
            "mode": "real",
        },
    )

    async def _invoke(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        # Channel-level adapter is a thin passthrough — all the
        # tenant-scope / signature validation / metrics live in the
        # server's wrapped closure, which is what ``invoke`` is.
        return await invoke(payload)

    async def _stop() -> None:
        # W25 ships in-process handler form; no socket to close here.
        logger.info(
            "serving.channel.rest.stop",
            extra={
                "channel": "rest",
                "server_id": server_id,
                "tenant_id": tenant_id,
                "model": model_name,
                "model_version": model_version,
                "mode": "real",
            },
        )

    return ChannelBinding(
        channel="rest",
        uri=uri,
        invoke=_invoke,
        stop=_stop,
        info={"host": host, "port": port},
    )


def health_response(*, model_name: str, model_version: int) -> Mapping[str, Any]:
    """Return the canonical ``GET /health`` body for a bound REST channel.

    Per W25 invariant 4 — ``GET /health → 200`` is served whenever the
    model is registered. Exposed as a helper so Nexus mounts can drop
    it into the ``/ml/predict/<model>/health`` route in W26+ without
    re-deriving the shape.
    """
    return {
        "status": "healthy",
        "model": model_name,
        "model_version": model_version,
    }
