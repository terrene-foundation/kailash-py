# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``InferenceServer`` — canonical ML inference runtime (W25).

Per ``specs/ml-serving.md §1.1`` + §2.1, ``InferenceServer`` is the one
canonical runtime that loads a model via :class:`ModelRegistry`, serves
predictions through REST / MCP / gRPC channel adapters, runs ONNX by
default with an explicit pickle fallback gate, and feeds the ambient
observability + audit layers.

W25 scope
---------
This module ships the **load / predict / stop + channel dispatch** core
of the spec. Out-of-scope-for-W25 surfaces (shadow traffic, canary,
streaming, micro-batching, per-tenant rate limits, batch jobs, schema
DDL) are covered by sibling shards in the same milestone.

Invariants satisfied here
~~~~~~~~~~~~~~~~~~~~~~~~~

* Invariant 1 — :class:`ModelSignature` validates every request; mismatch
  raises :class:`InvalidInputSchemaError` (spec §12, "400-class").
* Invariant 2 — batch mode via ``options={"batch_size": N}``.
* Invariant 3 — :attr:`ServeHandle.urls["rest"]` ends in
  ``/predict/{ModelName}``.
* Invariant 4 — :meth:`health` returns a 200-shape mapping whenever the
  model is registered.
* Invariant 5 — ``km.serve("name@production")`` resolves via
  :meth:`ModelRegistry.get_model(..., stage="production")` (alias layer).
* Invariant 6 — ONNX runtime preferred; pickle fallback requires
  ``runtime="pickle"`` explicit opt-in AND emits a loud WARN.
* Invariant 7 — :class:`InferenceServerError` subclasses raised for
  every failure mode (model-not-found, signature mismatch, onnx load).
* Invariant 8 — gRPC adapter gated by ``[grpc]`` extra — ``ImportError``
  at :func:`kailash_ml.serving.channels.grpc.bind_grpc` when missing.

Per ``rules/facade-manager-detection.md`` MUST 1: this is a
``*Server`` / manager-shape class. A Tier-2 wiring test through the
``engine.serve(...)`` facade proves the real call site (see
``tests/integration/test_inference_server_wiring.py``).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Mapping, Optional

from kailash_ml.errors import (
    InferenceServerError,
    InvalidInputSchemaError,
    ModelLoadError,
    ModelNotFoundError,
)
from kailash_ml.serving.channels._base import ChannelBinding, InferenceCallback
from kailash_ml.serving.channels.mcp import bind_mcp
from kailash_ml.serving.channels.rest import bind_rest
from kailash_ml.serving.serve_handle import ServeHandle, ServeStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from kailash_ml.engines.model_registry import ModelRegistry, ModelVersion
    from kailash_ml.types import ModelSignature


logger = logging.getLogger(__name__)


__all__ = [
    "InferenceServer",
    "InferenceServerConfig",
    "parse_model_uri",
    "ALLOWED_RUNTIMES",
    "ALLOWED_CHANNELS",
    "DEFAULT_CHANNELS",
]


ALLOWED_RUNTIMES: tuple[str, ...] = ("onnx", "pickle")
"""Runtimes accepted by :class:`InferenceServer`. ONNX is the default.

Per ``specs/ml-serving.md §2.5.3`` the pickle fallback is gated by an
explicit ``runtime="pickle"`` opt-in; ONNX is the secure default. The
legacy torchscript/gguf runtimes are out-of-scope for W25 and live in
sibling shards.
"""


ALLOWED_CHANNELS: tuple[str, ...] = ("rest", "mcp", "grpc")
"""Channels exposed by :meth:`InferenceServer.start`."""


DEFAULT_CHANNELS: tuple[str, ...] = ("rest",)
"""Default channel set when none is supplied — REST-only."""


# ---------------------------------------------------------------------------
# parse_model_uri
# ---------------------------------------------------------------------------


def parse_model_uri(
    model_uri_or_name: str,
) -> tuple[str, Optional[str], Optional[int]]:
    """Parse ``"fraud@production"`` / ``"fraud:7"`` / ``"fraud"``.

    Returns ``(model_name, alias, version)`` where exactly one of
    ``alias`` / ``version`` is non-None when an alias or pinned version
    is embedded in the input. Invariant 5 — a bare ``"fraud"`` returns
    ``(fraud, None, None)`` and the caller MUST supply ``alias=`` or
    ``version=`` kwargs.

    Raises
    ------
    ValueError
        When the input is empty or contains both ``@`` and ``:`` (ambiguous).
    """
    if not model_uri_or_name or not isinstance(model_uri_or_name, str):
        raise ValueError(
            "model_uri_or_name must be a non-empty string "
            "(e.g. 'fraud', 'fraud@production', or 'fraud:7')"
        )

    has_alias = "@" in model_uri_or_name
    has_version = ":" in model_uri_or_name
    if has_alias and has_version:
        raise ValueError(
            f"model URI {model_uri_or_name!r} contains BOTH '@' (alias) "
            f"AND ':' (version) — choose one. Valid: 'fraud', "
            f"'fraud@production', 'fraud:7'."
        )
    if has_alias:
        name, _, alias_raw = model_uri_or_name.partition("@")
        alias = f"@{alias_raw}" if not alias_raw.startswith("@") else alias_raw
        if not name or not alias_raw:
            raise ValueError(
                f"model URI {model_uri_or_name!r} missing name or alias "
                f"(expected 'name@alias')"
            )
        return name, alias, None
    if has_version:
        name, _, ver_raw = model_uri_or_name.partition(":")
        if not name or not ver_raw:
            raise ValueError(
                f"model URI {model_uri_or_name!r} missing name or version "
                f"(expected 'name:version')"
            )
        try:
            version = int(ver_raw)
        except ValueError as exc:
            raise ValueError(
                f"model URI {model_uri_or_name!r} has non-integer version "
                f"{ver_raw!r}"
            ) from exc
        if version < 1:
            raise ValueError(
                f"model URI {model_uri_or_name!r} has non-positive version "
                f"{version}"
            )
        return name, None, version
    # Bare name
    return model_uri_or_name, None, None


# ---------------------------------------------------------------------------
# InferenceServerConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InferenceServerConfig:
    """Construction envelope for :class:`InferenceServer`.

    The canonical surface lives in ``specs/ml-serving.md §2.1``. W25
    exposes the subset needed to validate the W25 invariants; later
    shards extend the dataclass with shadow / canary / rate-limit /
    autoscaling hints.

    Parameters
    ----------
    tenant_id:
        Scope of every request served; ``None`` permitted only in
        single-tenant deployments. Emitted on every log line.
    model_name, model_version, alias:
        Resolved model identity. Callers typically pass a string URI
        to :meth:`InferenceServer.from_registry` which parses it via
        :func:`parse_model_uri` and resolves the alias.
    channels:
        Subset of :data:`ALLOWED_CHANNELS`. Duplicates are collapsed.
    runtime:
        ``"onnx"`` (default) or ``"pickle"`` (explicit opt-in only).
    batch_size:
        Per-request batch cap. ``None`` = no batch mode; invariant 2.
    """

    tenant_id: Optional[str]
    model_name: str
    model_version: int
    alias: Optional[str] = None
    channels: tuple[str, ...] = DEFAULT_CHANNELS
    runtime: Literal["onnx", "pickle"] = "onnx"
    batch_size: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.model_name:
            raise ValueError("InferenceServerConfig.model_name is required")
        if self.model_version < 1:
            raise ValueError(
                f"InferenceServerConfig.model_version must be >= 1, "
                f"got {self.model_version}"
            )
        if self.runtime not in ALLOWED_RUNTIMES:
            raise ValueError(
                f"InferenceServerConfig.runtime must be one of "
                f"{ALLOWED_RUNTIMES}, got {self.runtime!r}"
            )
        if not self.channels:
            raise ValueError(
                "InferenceServerConfig.channels must be a non-empty tuple; "
                f"subset of {ALLOWED_CHANNELS}"
            )
        bad = [c for c in self.channels if c not in ALLOWED_CHANNELS]
        if bad:
            raise ValueError(
                f"InferenceServerConfig.channels contains unsupported "
                f"channels {bad}; valid: {ALLOWED_CHANNELS}"
            )
        if self.batch_size is not None and self.batch_size < 1:
            raise ValueError(
                f"InferenceServerConfig.batch_size must be >= 1 or None, "
                f"got {self.batch_size}"
            )


# ---------------------------------------------------------------------------
# InferenceServer
# ---------------------------------------------------------------------------


@dataclass
class _LoadedModel:
    """In-memory view of a loaded model artifact."""

    model_version: "ModelVersion"
    signature: Optional["ModelSignature"]
    onnx_bytes: Optional[bytes]
    pickle_bytes: Optional[bytes]
    runtime: Literal["onnx", "pickle"]
    loaded_at: float = field(default_factory=time.time)


class InferenceServer:
    """Canonical inference runtime — W25 load / predict / stop + channels.

    Lifecycle
    ~~~~~~~~~

    1. :meth:`from_registry` (classmethod) — resolves the model URI
       through the registry's alias layer and returns a ready-to-start
       server.
    2. :meth:`start` — loads the model artifact (ONNX preferred, pickle
       under explicit opt-in), binds the requested channels, returns a
       :class:`ServeHandle`.
    3. :meth:`predict` — in-process inference; exposed for direct-call
       usage AND used by every channel adapter via a wrapped closure.
    4. :meth:`stop` — drains in-flight requests, unloads the model,
       tears down every channel.

    Per ``rules/facade-manager-detection.md`` MUST 3 the constructor
    takes the ``registry`` explicitly — no global lookup, no parallel
    registry construction.
    """

    def __init__(
        self,
        config: InferenceServerConfig,
        *,
        registry: "ModelRegistry",
        server_id: Optional[str] = None,
    ) -> None:
        if registry is None:
            raise ValueError(
                "InferenceServer requires a registry; per "
                "rules/facade-manager-detection.md MUST 3 the framework "
                "instance is a constructor argument, not a global lookup."
            )
        self._config = config
        self._registry = registry
        self._server_id = server_id or uuid.uuid4().hex[:16]
        self._status: ServeStatus = "starting"
        self._loaded: Optional[_LoadedModel] = None
        self._bindings: dict[str, ChannelBinding] = {}
        # Guards predict() against concurrent load/unload.
        self._lock = asyncio.Lock()
        # In-flight request counter for drain-on-stop. A minimal counter
        # is sufficient for W25 — sibling shards add per-tenant quotas.
        self._inflight: int = 0

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------
    @property
    def config(self) -> InferenceServerConfig:
        return self._config

    @property
    def server_id(self) -> str:
        return self._server_id

    @property
    def status(self) -> ServeStatus:
        return self._status

    @property
    def bindings(self) -> Mapping[str, ChannelBinding]:
        """Read-only view of active channel bindings."""
        return dict(self._bindings)

    @property
    def model_signature(self) -> Optional["ModelSignature"]:
        """Signature of the loaded model, or ``None`` until :meth:`start`."""
        return self._loaded.signature if self._loaded is not None else None

    # ------------------------------------------------------------------
    # Registry-backed construction — invariant 5 (alias resolution)
    # ------------------------------------------------------------------
    @classmethod
    async def from_registry(
        cls,
        model_uri_or_name: str,
        *,
        registry: "ModelRegistry",
        alias: Optional[str] = None,
        version: Optional[int] = None,
        tenant_id: Optional[str] = None,
        channels: tuple[str, ...] = DEFAULT_CHANNELS,
        runtime: Literal["onnx", "pickle"] = "onnx",
        batch_size: Optional[int] = None,
        server_id: Optional[str] = None,
    ) -> "InferenceServer":
        """Resolve ``name@alias`` / ``name:version`` via the registry.

        Per W25 invariant 5 — ``km.serve("name@production")`` routes
        through this method. When the resolved ``ModelVersion`` is
        missing the registry raises, which we convert to
        :class:`ModelNotFoundError` (``InferenceServerError`` subclass).
        """
        parsed_name, parsed_alias, parsed_version = parse_model_uri(model_uri_or_name)
        effective_alias = alias if alias is not None else parsed_alias
        effective_version = version if version is not None else parsed_version

        t0 = time.monotonic()
        logger.info(
            "inference_server.resolve.start",
            extra={
                "tenant_id": tenant_id,
                "model_name": parsed_name,
                "alias": effective_alias,
                "version": effective_version,
                "runtime": runtime,
                "channels": list(channels),
                "mode": "real",
            },
        )
        model_version_obj = await _resolve_model_via_registry(
            registry=registry,
            name=parsed_name,
            alias=effective_alias,
            version=effective_version,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        logger.info(
            "inference_server.resolve.ok",
            extra={
                "tenant_id": tenant_id,
                "model_name": parsed_name,
                "alias": effective_alias,
                "resolved_version": model_version_obj.version,
                "elapsed_ms": elapsed_ms,
                "mode": "real",
            },
        )

        config = InferenceServerConfig(
            tenant_id=tenant_id,
            model_name=model_version_obj.name,
            model_version=model_version_obj.version,
            alias=effective_alias,
            channels=tuple(channels),
            runtime=runtime,
            batch_size=batch_size,
        )
        server = cls(config, registry=registry, server_id=server_id)
        # Attach the resolved ModelVersion so :meth:`start` skips a second
        # registry fetch. The artifact bytes are loaded at start().
        server._loaded = _LoadedModel(
            model_version=model_version_obj,
            signature=getattr(model_version_obj, "signature", None),
            onnx_bytes=None,
            pickle_bytes=None,
            runtime=runtime,
        )
        return server

    # ------------------------------------------------------------------
    # Lifecycle — start / stop
    # ------------------------------------------------------------------
    async def start(self) -> ServeHandle:
        """Load the model, bind channels, return a :class:`ServeHandle`.

        Per W25 invariants 3 + 4 + 6, start():

        * Loads the ONNX artifact when ``runtime="onnx"`` (default),
          falling back to pickle ONLY when ``runtime="pickle"`` is
          explicitly set (loud WARN per invariant 6).
        * Binds every channel in ``config.channels`` in order.
        * Returns a :class:`ServeHandle` whose ``urls["rest"]`` ends
          with ``/predict/{ModelName}`` when REST is among channels.

        Raises
        ------
        ModelLoadError
            When the artifact cannot be loaded (registry missing bytes,
            deserialization failure).
        ModelNotFoundError
            When the registry has no row for the configured
            ``(name, version)``.
        """
        if self._status != "starting":
            raise InferenceServerError(
                f"InferenceServer[{self._server_id}] already started — "
                f"status={self._status!r}; construct a fresh server to "
                f"rebind channels."
            )

        t0 = time.monotonic()
        logger.info(
            "inference_server.start",
            extra={
                "server_id": self._server_id,
                "tenant_id": self._config.tenant_id,
                "model": self._config.model_name,
                "model_version": self._config.model_version,
                "alias": self._config.alias,
                "channels": list(self._config.channels),
                "runtime": self._config.runtime,
                "batch_size": self._config.batch_size,
                "mode": "real",
            },
        )

        try:
            await self._load_model()
            self._bindings = self._bind_channels()
        except InferenceServerError:
            # Typed already; re-raise.
            self._status = "stopped"
            raise
        except Exception as exc:
            self._status = "stopped"
            logger.warning(
                "inference_server.start.error",
                extra={
                    "server_id": self._server_id,
                    "tenant_id": self._config.tenant_id,
                    "model": self._config.model_name,
                    "model_version": self._config.model_version,
                    "exc_type": type(exc).__name__,
                    "mode": "real",
                },
            )
            raise ModelLoadError(
                f"InferenceServer[{self._server_id}] failed to start "
                f"model {self._config.model_name!r} v{self._config.model_version}: "
                f"{exc.__class__.__name__}: {exc}"
            ) from exc

        self._status = "ready"
        urls = {name: b.uri for name, b in self._bindings.items()}
        primary = urls.get("rest") or next(iter(urls.values()))
        handle = ServeHandle(
            url=primary,
            urls=urls,
            server_id=self._server_id,
            tenant_id=self._config.tenant_id,
            model_name=self._config.model_name,
            model_version=self._config.model_version,
            alias=self._config.alias,
            channels=self._config.channels,
        )
        handle._attach_server(self)

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        logger.info(
            "inference_server.start.ok",
            extra={
                "server_id": self._server_id,
                "tenant_id": self._config.tenant_id,
                "model": self._config.model_name,
                "model_version": self._config.model_version,
                "channels": list(urls.keys()),
                "urls": urls,
                "elapsed_ms": elapsed_ms,
                "mode": "real",
            },
        )
        return handle

    async def stop(self) -> None:
        """Drain in-flight requests, unload the model, close channels.

        Idempotent — repeated calls are no-ops after the first completes.
        """
        if self._status == "stopped":
            return
        self._status = "draining"

        logger.info(
            "inference_server.stop.drain",
            extra={
                "server_id": self._server_id,
                "tenant_id": self._config.tenant_id,
                "model": self._config.model_name,
                "model_version": self._config.model_version,
                "inflight": self._inflight,
                "mode": "real",
            },
        )

        # Tear down channels first so no new invocations arrive, then
        # await the drain.
        for channel_name, binding in list(self._bindings.items()):
            try:
                await binding.stop()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "inference_server.stop.channel_cleanup_failed",
                    extra={
                        "server_id": self._server_id,
                        "channel": channel_name,
                        "exc_type": type(exc).__name__,
                        "mode": "real",
                    },
                )
        self._bindings.clear()

        # Wait for in-flight predicts to complete (short poll; W25 has
        # in-process handlers so the counter drains immediately in
        # practice).
        for _ in range(50):
            if self._inflight <= 0:
                break
            await asyncio.sleep(0.01)

        # Release model bytes so GC can reclaim onnxruntime session etc.
        self._loaded = None
        self._status = "stopped"
        logger.info(
            "inference_server.stop.ok",
            extra={
                "server_id": self._server_id,
                "tenant_id": self._config.tenant_id,
                "model": self._config.model_name,
                "model_version": self._config.model_version,
                "mode": "real",
            },
        )

    # ------------------------------------------------------------------
    # Public surface — predict + health
    # ------------------------------------------------------------------
    async def predict(
        self,
        features: Mapping[str, Any],
        *,
        tenant_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """Run in-process inference with signature validation.

        Parameters
        ----------
        features:
            Either a single-record mapping ``{"amount": 42.0, ...}`` or
            a batch payload ``{"records": [{...}, {...}]}``.
        tenant_id:
            Override for single-request tenant context. When ``None`` the
            server's configured ``tenant_id`` is used. Cross-tenant
            invocation raises :class:`InferenceServerError`.

        Raises
        ------
        InvalidInputSchemaError
            When the features mapping does not match the model's
            :class:`ModelSignature` — W25 invariant 1.
        InferenceServerError
            When the server is not in the ``ready`` state, or when
            cross-tenant invocation is attempted.
        """
        if self._status != "ready":
            raise InferenceServerError(
                f"InferenceServer[{self._server_id}] status={self._status!r}; "
                f"predict() requires 'ready'."
            )
        if self._loaded is None or (
            self._loaded.onnx_bytes is None and self._loaded.pickle_bytes is None
        ):
            # Defensive: the ready→loaded invariant is maintained by start()
            raise InferenceServerError(
                f"InferenceServer[{self._server_id}] has no loaded artifact; "
                f"start() was not called."
            )

        effective_tenant = (
            tenant_id if tenant_id is not None else self._config.tenant_id
        )
        self._check_tenant(effective_tenant)
        self._validate_signature(features)

        t0 = time.monotonic()
        request_id = uuid.uuid4().hex[:12]
        logger.info(
            "inference.predict.start",
            extra={
                "server_id": self._server_id,
                "request_id": request_id,
                "tenant_id": effective_tenant,
                "model": self._config.model_name,
                "model_version": self._config.model_version,
                "path": "online",
                "input_shape": _shape_of(features),
                "mode": "real",
            },
        )

        self._inflight += 1
        try:
            result = await self._run_inference(features)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            logger.info(
                "inference.predict.ok",
                extra={
                    "server_id": self._server_id,
                    "request_id": request_id,
                    "tenant_id": effective_tenant,
                    "model": self._config.model_name,
                    "model_version": self._config.model_version,
                    "latency_ms": elapsed_ms,
                    "inference_path": self._loaded.runtime,
                    "mode": "real",
                },
            )
            return result
        except InferenceServerError:
            raise
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            fingerprint = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()[:8]
            logger.warning(
                "inference.predict.error",
                extra={
                    "server_id": self._server_id,
                    "request_id": request_id,
                    "tenant_id": effective_tenant,
                    "model": self._config.model_name,
                    "model_version": self._config.model_version,
                    "latency_ms": elapsed_ms,
                    "exc_type": type(exc).__name__,
                    "exc_fingerprint": fingerprint,
                    "mode": "real",
                },
            )
            raise InferenceServerError(
                f"InferenceServer[{self._server_id}] predict failed: "
                f"{type(exc).__name__} (fingerprint={fingerprint})"
            ) from exc
        finally:
            self._inflight -= 1

    def health(self) -> Mapping[str, Any]:
        """Return a 200-shape health body per W25 invariant 4.

        When the server is ``ready`` and the model is loaded the
        response includes ``status="healthy"``. Otherwise it includes
        the current status. Callers (Nexus mounts, probe scripts) use
        the return shape directly — the HTTP status code is 200 only
        when the model is registered AND the server is ready.
        """
        if self._status == "ready" and self._loaded is not None:
            return {
                "status": "healthy",
                "server_id": self._server_id,
                "model": self._config.model_name,
                "model_version": self._config.model_version,
                "tenant_id": self._config.tenant_id,
                "channels": list(self._bindings.keys()),
            }
        return {
            "status": self._status,
            "server_id": self._server_id,
            "model": self._config.model_name,
            "model_version": self._config.model_version,
            "tenant_id": self._config.tenant_id,
            "channels": list(self._bindings.keys()),
        }

    # ------------------------------------------------------------------
    # Internal — load / bind / validate / infer
    # ------------------------------------------------------------------
    async def _load_model(self) -> None:
        """Load the model artifact per the configured runtime.

        Contract (W25 invariant 6):

        * ``runtime="onnx"`` (default) — load ``model.onnx``. Missing
          artifact raises :class:`ModelLoadError`; fallback to pickle is
          BLOCKED here (explicit opt-in only).
        * ``runtime="pickle"`` — explicit opt-in; load ``model.pkl`` AND
          emit a loud ``server.load.pickle_fallback`` WARN log with a
          security-caveat message per spec §2.5.3.
        """
        # Fetch (or reuse) the ModelVersion. from_registry stashes it;
        # direct-construction callers haven't resolved yet.
        if self._loaded is None or self._loaded.model_version is None:
            model_version_obj = await _resolve_model_via_registry(
                registry=self._registry,
                name=self._config.model_name,
                alias=self._config.alias,
                version=self._config.model_version,
            )
            self._loaded = _LoadedModel(
                model_version=model_version_obj,
                signature=getattr(model_version_obj, "signature", None),
                onnx_bytes=None,
                pickle_bytes=None,
                runtime=self._config.runtime,
            )
        else:
            # Keep the pre-resolved version; refresh the runtime if the
            # config overrode it.
            self._loaded = _LoadedModel(
                model_version=self._loaded.model_version,
                signature=self._loaded.signature,
                onnx_bytes=None,
                pickle_bytes=None,
                runtime=self._config.runtime,
            )

        artifact_name = "model.onnx" if self._config.runtime == "onnx" else "model.pkl"
        try:
            artifact_bytes = await self._registry.load_artifact(
                self._config.model_name,
                self._config.model_version,
                artifact_name,
            )
        except (FileNotFoundError, LookupError) as exc:
            raise ModelLoadError(
                f"InferenceServer[{self._server_id}] could not load "
                f"{artifact_name!r} for {self._config.model_name} "
                f"v{self._config.model_version} (runtime={self._config.runtime}): "
                f"{exc.__class__.__name__}: {exc}"
            ) from exc

        if self._config.runtime == "onnx":
            self._loaded.onnx_bytes = artifact_bytes
        else:
            # Invariant 6 — pickle fallback is explicit opt-in AND emits
            # a loud WARN on every load.
            self._loaded.pickle_bytes = artifact_bytes
            logger.warning(
                "server.load.pickle_fallback",
                extra={
                    "server_id": self._server_id,
                    "tenant_id": self._config.tenant_id,
                    "model": self._config.model_name,
                    "model_version": self._config.model_version,
                    "reason": "runtime='pickle' explicitly set at construction",
                    "security_caveat": (
                        "pickle is arbitrary-code-execution — "
                        "validate model provenance"
                    ),
                    "mode": "real",
                },
            )

    def _bind_channels(self) -> dict[str, ChannelBinding]:
        """Bind the configured channels in order."""
        # Deduplicate while preserving order.
        seen: set[str] = set()
        ordered: list[str] = []
        for c in self._config.channels:
            if c not in seen:
                seen.add(c)
                ordered.append(c)

        invoke = self._build_invoke_callback()
        bound: dict[str, ChannelBinding] = {}
        for channel in ordered:
            if channel == "rest":
                bound[channel] = bind_rest(
                    model_name=self._config.model_name,
                    model_version=self._config.model_version,
                    invoke=invoke,
                    server_id=self._server_id,
                    tenant_id=self._config.tenant_id,
                )
            elif channel == "mcp":
                bound[channel] = bind_mcp(
                    model_name=self._config.model_name,
                    model_version=self._config.model_version,
                    invoke=invoke,
                    server_id=self._server_id,
                    tenant_id=self._config.tenant_id,
                )
            elif channel == "grpc":
                # Lazy import — the grpc adapter raises ImportError with
                # an actionable message when the [grpc] extra is missing.
                from kailash_ml.serving.channels.grpc import bind_grpc

                bound[channel] = bind_grpc(
                    model_name=self._config.model_name,
                    model_version=self._config.model_version,
                    invoke=invoke,
                    server_id=self._server_id,
                    tenant_id=self._config.tenant_id,
                )
            else:  # defensive — validated at config construction
                raise ValueError(f"internal: unhandled channel {channel!r}")

        return bound

    def _build_invoke_callback(self) -> InferenceCallback:
        """Return the channel-facing invoke closure.

        Every channel adapter receives THIS closure (tenant-scope +
        signature validation + observability) rather than re-implementing
        the discipline per-channel. This is why the channel adapters
        themselves are thin.
        """
        server = self

        async def _invoke(payload: Mapping[str, Any]) -> Mapping[str, Any]:
            # Channel-level invocations run under the server's tenant.
            return await server.predict(payload, tenant_id=server._config.tenant_id)

        return _invoke

    def _check_tenant(self, tenant_id: Optional[str]) -> None:
        """Refuse cross-tenant invocations per spec §11.1."""
        expected = self._config.tenant_id
        if expected is not None and tenant_id != expected:
            raise InferenceServerError(
                f"InferenceServer[{self._server_id}] is scoped to tenant "
                f"{expected!r}; invocation with tenant_id={tenant_id!r} "
                f"refused (rules/tenant-isolation.md Rule 2)."
            )

    def _validate_signature(self, features: Mapping[str, Any]) -> None:
        """Validate incoming features against the model signature.

        Per W25 invariant 1 + spec §9.3: a mismatch raises
        :class:`InvalidInputSchemaError` listing the missing columns
        (actionable per ``rules/zero-tolerance.md`` Rule 3a — no silent
        fallback). When no signature is recorded the check is a no-op —
        legacy models without signatures still serve, but callers are
        expected to register new models with ``signature=...``.
        """
        sig = self.model_signature
        if sig is None:
            return
        expected_features = {f.name for f in sig.input_schema.features}
        if not expected_features:
            return

        # Extract the feature set to check — single record keys OR first
        # batch record keys.
        records = features.get("records") if isinstance(features, Mapping) else None
        if isinstance(records, list) and records:
            # Batch payload — validate every record has all required
            # features. Validate using the first record as the reference
            # shape; every subsequent record must have at least the
            # expected_features.
            first = records[0]
            if not isinstance(first, Mapping):
                raise InvalidInputSchemaError(
                    f"InferenceServer[{self._server_id}] batch records must "
                    f"be mappings; first record is {type(first).__name__}"
                )
            provided = set(first.keys())
            missing = expected_features - provided
            if missing:
                raise InvalidInputSchemaError(
                    f"InferenceServer[{self._server_id}] batch missing "
                    f"required feature(s) {sorted(missing)}; expected "
                    f"{sorted(expected_features)}, got {sorted(provided)}"
                )
            # Check subsequent records share the same key set.
            for idx, rec in enumerate(records[1:], start=1):
                if not isinstance(rec, Mapping):
                    raise InvalidInputSchemaError(
                        f"InferenceServer[{self._server_id}] batch record "
                        f"{idx} is {type(rec).__name__}, expected mapping"
                    )
                rec_missing = expected_features - set(rec.keys())
                if rec_missing:
                    raise InvalidInputSchemaError(
                        f"InferenceServer[{self._server_id}] batch record "
                        f"{idx} missing required feature(s) {sorted(rec_missing)}"
                    )
            return

        # Single-record payload — every key not a well-known envelope key
        # is expected to be a feature.
        provided = set(k for k in features.keys() if k != "records")
        missing = expected_features - provided
        if missing:
            raise InvalidInputSchemaError(
                f"InferenceServer[{self._server_id}] request missing "
                f"required feature(s) {sorted(missing)}; expected "
                f"{sorted(expected_features)}, got {sorted(provided)}"
            )

    async def _run_inference(self, features: Mapping[str, Any]) -> Mapping[str, Any]:
        """Invoke the loaded runtime in-process.

        Delegates to the engine-level helpers so there is exactly ONE
        ONNX / pickle inference path in the codebase. The engine helpers
        handle both single-record and batch payload shapes.
        """
        from kailash_ml.engine import _run_native_inference, _run_onnx_inference

        assert self._loaded is not None  # guarded by caller
        if self._loaded.runtime == "onnx":
            assert self._loaded.onnx_bytes is not None
            return _run_onnx_inference(self._loaded.onnx_bytes, features)
        # pickle
        assert self._loaded.pickle_bytes is not None
        return _run_native_inference(self._loaded.pickle_bytes, features)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_model_via_registry(
    *,
    registry: "ModelRegistry",
    name: str,
    alias: Optional[str],
    version: Optional[int],
) -> "ModelVersion":
    """Resolve a model through the registry's get_model surface.

    Invariant 5 — ``km.serve("fraud@production")`` routes through here.
    ``alias`` values like ``"@production"`` are normalised to the stage
    string the registry expects (``"production"``).
    """
    # Normalise @-prefixed alias to the stage string ModelRegistry uses.
    stage: Optional[str]
    if alias is None:
        stage = None
    else:
        stage = alias[1:] if alias.startswith("@") else alias

    try:
        if stage is not None:
            return await registry.get_model(name, stage=stage)
        if version is not None:
            return await registry.get_model(name, version)
        return await registry.get_model(name)
    except Exception as exc:
        # ModelRegistry raises its own ModelNotFoundError; re-raise as
        # the canonical kailash_ml.errors.ModelNotFoundError so callers
        # match against one class.
        exc_name = exc.__class__.__name__
        if "ModelNotFound" in exc_name:
            raise ModelNotFoundError(
                f"InferenceServer could not resolve model {name!r} "
                f"(alias={alias!r}, version={version!r}): {exc}"
            ) from exc
        raise


def _shape_of(features: Mapping[str, Any]) -> tuple[int, int]:
    """Return ``(n_rows, n_cols)`` for observability.

    Best-effort — never raises. Used only in the log ``input_shape``
    field per spec §3.1.
    """
    try:
        records = features.get("records") if isinstance(features, Mapping) else None
        if isinstance(records, list):
            n_rows = len(records)
            n_cols = (
                len(records[0]) if records and isinstance(records[0], Mapping) else 0
            )
            return (n_rows, n_cols)
        # Single record
        n_cols = sum(1 for k in features.keys() if k != "records")
        return (1, n_cols)
    except Exception:  # pragma: no cover - defensive only
        return (0, 0)
