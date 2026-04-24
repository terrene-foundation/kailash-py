# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ONNX export probe for :class:`ModelRegistry` (``specs/ml-registry.md`` §5.6).

The probe splits into two responsibilities:

1. **Export** — turn a trained model into ONNX bytes. :class:`OnnxBridge`
   already handles six families (sklearn, xgboost, lightgbm, torch,
   lightning, catboost) and ships with kailash-ml. The probe exposes
   :func:`export_to_onnx` as a thin wrapper that routes through the
   bridge, translates bridge failures into typed
   :class:`OnnxExportError` / :class:`OnnxExportUnsupportedOpsError`,
   and materializes bytes regardless of whether the bridge prefers a
   file-based or in-memory path for a given framework.

2. **Classify** — parse the resulting bytes into the registry-ready
   ``OnnxProbeResult``. :func:`classify_onnx_bytes` parses
   ``ModelProto.opset_import`` into ``{domain: version}``, resolves
   any non-default domain to an ``ort-extensions`` package name per
   the §5.6.1 step-4 mapping, and emits ``onnx_status="clean"`` or
   ``"custom_ops"``. The ``"legacy_pickle_only"`` value from §5.6.2 is
   the registry's fallback disposition when it catches an
   :class:`OnnxExportError` under ``allow_pickle_fallback=True``; the
   probe itself never produces that value — a clean separation of
   concerns that keeps silent-pickle regressions (plan invariant 5)
   structurally impossible from the probe surface.

Call order in the registry plumbing:

.. code-block:: python

    onnx_bytes = export_to_onnx(trainable, framework=..., sample_input=...)
    result = classify_onnx_bytes(onnx_bytes)
    # registry writes result.onnx_bytes to the ArtifactStore, persists
    # result.opset_imports / ort_extensions / onnx_status into
    # _kml_model_versions.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "OnnxExportError",
    "OnnxExportUnsupportedOpsError",
    "OnnxProbeResult",
    "classify_onnx_bytes",
    "export_to_onnx",
    "resolve_ort_extensions",
]

logger = logging.getLogger(__name__)


# --- Exceptions -----------------------------------------------------------


class OnnxExportError(ValueError):
    """ONNX export failed during the registry probe (§5.6 / plan inv 4).

    Carries ``framework`` (the export family that raised) and ``cause``
    (the underlying exception's message, with traceback preserved via
    ``__cause__``). Matches the :class:`ValueError`-subclass convention
    used by :mod:`kailash_ml.tracking.registry` so callers handling
    ``ModelRegistryError`` catch this too without importing the probe.
    """

    def __init__(self, *, framework: str, cause: str) -> None:
        super().__init__(
            f"ONNX export failed — framework={framework!r} cause={cause!r}"
        )
        self.framework = framework
        self.cause = cause


class OnnxExportUnsupportedOpsError(OnnxExportError):
    """Subclass for the ``legacy_pickle_only`` branch (§5.6.2).

    Distinct from the base so callers that only want pickle fallback on
    unsupported-ops failures can catch the narrower exception. Generic
    export failures (OOM, missing dep, I/O) raise the base class so
    they surface rather than silently collapsing into pickle.
    """

    def __init__(self, *, framework: str, unsupported_ops: list[str]) -> None:
        super().__init__(
            framework=framework,
            cause=f"unsupported_ops={sorted(set(unsupported_ops))!r}",
        )
        self.unsupported_ops: list[str] = sorted(set(unsupported_ops))


# --- Probe result ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OnnxProbeResult:
    """What the probe returns to the registry on a successful export.

    Every field maps 1:1 to a column the registry persists to
    ``_kml_model_versions`` (§5A.2) so the registry plumbing is a
    no-translation pass-through.
    """

    onnx_bytes: bytes
    sha256_hex: str
    onnx_status: Literal["clean", "custom_ops"]
    opset_imports: dict[str, int]
    ort_extensions: list[str] = field(default_factory=list)


# --- Ort-extensions mapping ----------------------------------------------


# §5.6.1 step 4: "if ANY domain other than the default '' appears in
# opset_imports (i.e. a custom-op domain is encountered), the registry
# MUST resolve the required ort-extensions-family package names". This
# is the single source of truth for the mapping; extend here as more
# custom-op families land.
_CUSTOM_DOMAIN_TO_EXTENSION: dict[str, str] = {
    "com.microsoft": "onnxruntime_extensions",
}


# The opset-import entries that carry standard ONNX ops and therefore
# require no ort-extensions. Empty string is the canonical "default"
# domain in the protobuf; "ai.onnx*" are the same family under the
# semantic name used by some exporters.
_STANDARD_DOMAINS = frozenset({"", "ai.onnx", "ai.onnx.ml", "ai.onnx.training"})


def resolve_ort_extensions(opset_imports: dict[str, int]) -> list[str]:
    """Map non-default opset-import domains → required extension packages.

    Returns an empty list when every domain is standard. Unknown custom
    domains produce a WARN log line but do NOT raise — serving fails
    with a typed error later per ``ml-serving §2.5.1``, and the probe
    should not crash registration on an otherwise-valid model.
    """
    extensions: list[str] = []
    seen: set[str] = set()
    for domain in sorted(opset_imports):
        if domain in _STANDARD_DOMAINS:
            continue
        pkg = _CUSTOM_DOMAIN_TO_EXTENSION.get(domain)
        if pkg is None:
            logger.warning(
                "onnx_probe.unknown_custom_domain",
                extra={"domain": domain},
            )
            continue
        if pkg not in seen:
            extensions.append(pkg)
            seen.add(pkg)
    return extensions


# --- Opset parsing --------------------------------------------------------


def _parse_opset_imports(onnx_bytes: bytes) -> dict[str, int]:
    """Extract ``{domain: version}`` from serialized ``ModelProto``.

    ``onnx`` is a base dependency of ``kailash-ml[onnx]``; the lazy
    import pattern matches ``rules/dependencies.md`` § "Optional Extras
    with Loud Failure" so a missing extra surfaces as a descriptive
    :class:`ImportError` rather than a silent None.
    """
    try:
        import onnx  # noqa: PLC0415 — optional-extra lazy import
    except ImportError as exc:
        raise OnnxExportError(
            framework="onnx",
            cause="onnx package is required — install kailash-ml[onnx]",
        ) from exc
    model = onnx.load_from_string(onnx_bytes)
    return {oi.domain: int(oi.version) for oi in model.opset_import}


# --- Classify public surface ---------------------------------------------


def classify_onnx_bytes(onnx_bytes: bytes) -> OnnxProbeResult:
    """Parse+classify ONNX bytes into an :class:`OnnxProbeResult`.

    The caller is responsible for producing ``onnx_bytes`` via
    whichever exporter suits their framework. The registry uses
    :func:`export_to_onnx` below which routes through
    :class:`OnnxBridge`; tests MAY pass a hand-crafted ``ModelProto``
    serialization directly.
    """
    if not isinstance(onnx_bytes, (bytes, bytearray)):
        raise OnnxExportError(
            framework="<unknown>",
            cause=f"onnx_bytes must be bytes (got {type(onnx_bytes).__name__})",
        )
    if not onnx_bytes:
        raise OnnxExportError(
            framework="<unknown>",
            cause="onnx_bytes is empty",
        )
    opset_imports = _parse_opset_imports(bytes(onnx_bytes))
    ort_extensions = resolve_ort_extensions(opset_imports)
    status: Literal["clean", "custom_ops"] = "custom_ops" if ort_extensions else "clean"
    digest = hashlib.sha256(onnx_bytes).hexdigest()
    return OnnxProbeResult(
        onnx_bytes=bytes(onnx_bytes),
        sha256_hex=digest,
        onnx_status=status,
        opset_imports=opset_imports,
        ort_extensions=ort_extensions,
    )


# --- Unsupported-ops heuristic -------------------------------------------


# Torch's exporter raises ``torch.onnx.errors.UnsupportedOperatorError``
# in modern versions; older versions raise a generic RuntimeError with
# "Exporting the operator X to ONNX opset version Y is not supported"
# in the message. The class-name check survives minor torch drift; the
# message pattern covers the legacy path.
_UNSUPPORTED_OP_CLASSNAMES: tuple[str, ...] = (
    "UnsupportedOperatorError",
    "UnsupportedOperator",
)


def _looks_like_unsupported_ops(exc: BaseException) -> list[str] | None:
    """Return op names if ``exc`` is an unsupported-op failure, else None.

    Walks ``__cause__`` / ``__context__`` so wrapping re-raises (e.g.
    the OnnxBridge's ``try/except Exception``) don't mask the typed
    underlying error.
    """
    seen: set[int] = set()
    cursor: BaseException | None = exc
    while cursor is not None and id(cursor) not in seen:
        seen.add(id(cursor))
        cls = type(cursor).__name__
        if cls in _UNSUPPORTED_OP_CLASSNAMES:
            op = (
                getattr(cursor, "operator_name", None)
                or getattr(cursor, "op_name", None)
                or str(cursor).split(":")[-1].strip()
            )
            return [op or "<unknown>"]
        msg = str(cursor)
        if "Exporting the operator" in msg and "not supported" in msg:
            # Parse "Exporting the operator <name> to ONNX opset..."
            parts = msg.split("Exporting the operator", 1)[1].split()
            if parts:
                return [parts[0].strip()]
            return ["<unknown>"]
        cursor = cursor.__cause__ or cursor.__context__
    return None


# --- Export public surface -----------------------------------------------


def export_to_onnx(
    model: Any,
    *,
    framework: str,
    sample_input: Any = None,
    n_features: int | None = None,
    schema: Any = None,
) -> bytes:
    """Run :class:`OnnxBridge` and return ONNX bytes.

    Strictly raises :class:`OnnxExportError` /
    :class:`OnnxExportUnsupportedOpsError` on any failure — silent
    success=False from the bridge is re-classified as the typed
    exception so callers don't accidentally skip registration on a
    failed export (§5.6.1 step 1 strict-export invariant).

    File-based export families (torch, lightning, catboost) write to a
    temp path and the probe reads it back — the registry path wants
    bytes so it can route through :class:`ArtifactStore.put`.
    """
    try:
        from kailash_ml.bridge.onnx_bridge import OnnxBridge  # noqa: PLC0415
    except ImportError as exc:
        raise OnnxExportError(
            framework=framework, cause=f"OnnxBridge import failed: {exc}"
        ) from exc

    bridge = OnnxBridge()
    import tempfile  # noqa: PLC0415

    tmp_path: Path | None = None
    try:
        if framework in ("torch", "lightning", "catboost"):
            # Bridge's file-based path is the most exercised; steer
            # into it so the same invariants (opset 17, dynamic axes)
            # apply regardless of caller.
            with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as fh:
                tmp_path = Path(fh.name)
        try:
            result = bridge.export(
                model,
                framework=framework,
                schema=schema,
                output_path=tmp_path,
                n_features=n_features,
                sample_input=sample_input,
            )
        except Exception as exc:
            ops = _looks_like_unsupported_ops(exc)
            if ops is not None:
                raise OnnxExportUnsupportedOpsError(
                    framework=framework, unsupported_ops=ops
                ) from exc
            raise OnnxExportError(framework=framework, cause=str(exc)) from exc
        if not result.success:
            ops = _looks_like_unsupported_ops(RuntimeError(result.error_message or ""))
            if ops is not None and result.onnx_status == "failed":
                raise OnnxExportUnsupportedOpsError(
                    framework=framework, unsupported_ops=ops
                )
            raise OnnxExportError(
                framework=framework,
                cause=result.error_message or "unknown bridge failure",
            )
        if tmp_path is not None and tmp_path.is_file():
            return tmp_path.read_bytes()
        # Tabular frameworks (sklearn/lightgbm/xgboost) return bytes
        # via the in-memory branch — re-invoke to fetch them (the
        # bridge's public ``export`` discards bytes after writing to
        # the path when ``output_path`` is None, so re-run to the
        # returned size-bytes path is fine; tabular exports are cheap).
        # The bridge returns bytes directly from the private helpers,
        # so we dispatch via the same names the bridge uses.
        size = result.model_size_bytes or 0
        if size <= 0:
            raise OnnxExportError(
                framework=framework,
                cause="bridge returned zero-size bytes",
            )
        # Re-materialize via tempfile for tabular families too so the
        # probe never reaches into bridge internals.
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as fh:
            tab_path = Path(fh.name)
        try:
            bridge.export(
                model,
                framework=framework,
                schema=schema,
                output_path=tab_path,
                n_features=n_features,
                sample_input=sample_input,
            )
            return tab_path.read_bytes()
        finally:
            tab_path.unlink(missing_ok=True)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
