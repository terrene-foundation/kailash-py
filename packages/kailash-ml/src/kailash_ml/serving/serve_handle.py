# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``ServeHandle`` — process-local handle returned by ``km.serve(...)``.

Per ``specs/ml-serving.md §2.3.3`` the ``ServeHandle`` is the user-visible
return type of ``km.serve(...)`` (and, via the engine delegation layer,
of ``engine.serve(...)``). It exposes the bound channel URIs, the
resolved ``(model_name, model_version, alias)`` tuple, the tenant_id
scope, an opaque ``server_id`` for administration, a ``status`` property,
and an async ``stop()`` for graceful shutdown.

W25 scope: the handle delegates to ``InferenceServer`` for the actual
channel lifecycle. Shadow / canary / streaming live elsewhere in the
serving package and are NOT exposed on ``ServeHandle`` directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:  # pragma: no cover - import-time optimisation
    from kailash_ml.serving.server import InferenceServer


logger = logging.getLogger(__name__)


ServeStatus = Literal["starting", "ready", "draining", "stopped"]


__all__ = ["ServeHandle", "ServeStatus"]


@dataclass(frozen=False, slots=True)
class ServeHandle:
    """Return envelope of ``km.serve(...)`` per ``ml-serving.md §2.3.3``.

    Invariants (per ``specs/ml-serving.md`` + W25 todo):

    * ``urls`` has per-channel entries. For every ``channel in channels``
      there MUST be a ``urls[channel]`` entry.
    * When ``rest`` is among ``channels``, ``urls["rest"]`` ends with
      ``/predict/{ModelName}`` per W25 invariant 3.
    * ``server_id`` is an opaque identifier; operators use it for
      administration (logs, metrics correlation).
    * ``stop()`` drains in-flight requests and unloads the model.
    """

    url: str  # primary channel URL (REST if available; else first channel)
    urls: dict[str, str]  # per-channel URLs, e.g. {"rest": "...", "mcp": "..."}
    server_id: str
    tenant_id: Optional[str]
    model_name: str
    model_version: int
    alias: Optional[str]
    channels: tuple[str, ...]

    # Internal wiring — set by the caller (km.serve / InferenceServer.start())
    # so ``stop()`` can tear down the channels bound at start-time.
    _server: Optional["InferenceServer"] = field(default=None, repr=False)
    _status: ServeStatus = field(default="ready", repr=False)

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------
    @property
    def status(self) -> ServeStatus:
        """Current lifecycle state of the underlying server."""
        if self._server is not None:
            # Delegate to the server if one is attached so operators see
            # the truth even if the handle was copied around.
            return self._server.status
        return self._status

    async def stop(self) -> None:
        """Gracefully shut down the backing ``InferenceServer``.

        Contract per ``ml-serving.md §2.3.3``:
        * Drain in-flight requests (InferenceServer owns the semantics).
        * Unload the model (release onnxruntime session / pickled bytes).
        * Transition status ``ready → draining → stopped``.

        Idempotent — repeated ``stop()`` calls emit an INFO log but do
        NOT raise.
        """
        if self._server is None:
            logger.info(
                "serve_handle.stop.noop",
                extra={
                    "reason": "no backing server attached",
                    "server_id": self.server_id,
                    "tenant_id": self.tenant_id,
                    "model": self.model_name,
                    "model_version": self.model_version,
                    "mode": "real",
                },
            )
            self._status = "stopped"
            return

        # Capture pre-stop status for the log line.
        previous = self._server.status
        logger.info(
            "serve_handle.stop.start",
            extra={
                "server_id": self.server_id,
                "tenant_id": self.tenant_id,
                "model": self.model_name,
                "model_version": self.model_version,
                "channels": list(self.channels),
                "previous_status": previous,
                "mode": "real",
            },
        )
        await self._server.stop()
        self._status = "stopped"
        logger.info(
            "serve_handle.stop.ok",
            extra={
                "server_id": self.server_id,
                "tenant_id": self.tenant_id,
                "model": self.model_name,
                "model_version": self.model_version,
                "mode": "real",
            },
        )

    # ------------------------------------------------------------------
    # Internal — used by the constructor facade (InferenceServer.start,
    # km.serve) to attach the backing server. Not part of the public API.
    # ------------------------------------------------------------------
    def _attach_server(self, server: "InferenceServer") -> None:
        """Attach (or re-attach) the backing ``InferenceServer``.

        Called exactly once by the constructor facade before the handle
        is returned to the caller.
        """
        self._server = server
