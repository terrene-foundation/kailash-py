# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Per-handler resolver chain for ``Nexus.handler_extract``.

This module owns the registration-time introspection + the per-invocation
resolution that backs the extractor surface. It is intentionally free of any
Nexus-instance import (no cycle): :func:`build_resolver_chain` is a pure
factory the ``Nexus.handler_extract`` method calls, returning a wrapper
function the existing ``register_handler`` path registers as a HandlerNode
workflow.

Design (per ``specs/nexus-fastapi-parity.md`` §97-142):

- At REGISTRATION, ``build_resolver_chain`` introspects ``func``'s parameters
  and classifies each as ``DEPENDS`` (default is a ``Depends`` marker),
  ``REQUEST`` (annotation resolves to the ``Request`` extractor), or ``FLAT``
  (everything else — same semantics as ``register_handler``). PEP 563 is
  detected here and raised LOUD.
- The returned ``wrapper`` exposes ONLY the FLAT params in its public
  signature, so the gateway maps HTTP-body inputs to them exactly as it does
  for a plain handler. Extractor params are NOT in the wrapper signature.
- At INVOCATION, the wrapper resolves each extractor param: ``Request`` is
  bound from the request ContextVar; each ``Depends(callable)`` is resolved
  ONCE per invocation (memoised) and recursively (the callable may itself take
  extractors). Then ``func`` is called with flat + resolved kwargs.

Resolver-error split-visibility (spec §134-142): a ``Depends`` callable that
raises is logged in full server-side and surfaced to the client as ONLY HTTP
500 (or the typed status if it raised ``NexusHandlerError``) + the canonical
``INTERNAL_ERROR`` envelope carrying a correlation id — never ``str(exc)`` /
class name / traceback / paths.
"""

import __future__

import inspect
import logging
import os
import uuid
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from nexus.context import get_current_request
from nexus.extractors import Bytes, Depends, Headers, NexusHandlerError, Request

logger = logging.getLogger(__name__)

# Parameter classification kinds.
_KIND_FLAT = "flat"
_KIND_REQUEST = "request"
_KIND_DEPENDS = "depends"
_KIND_HEADERS = "headers"
_KIND_BYTES = "bytes"


class ExtractorPEP563Error(TypeError):
    """Raised when a handler's module enabled the PEP 563 annotations future-import.

    Under PEP 563 the handler's annotation values are strings, not the
    extractor types, so the resolver cannot tell a ``Request`` parameter from a
    flat ``str``. The fix is to remove the stringized-annotation future-import
    from the handler's module (see ``docs/migration-fastapi.md`` §8).

    The message cites a WORKSPACE-RELATIVE path + line — never an absolute
    ``/Users/...`` path (PII hygiene, spec §313 LOW-S1).
    """


def _relative_handler_location(func: Callable) -> str:
    """Best-effort workspace-relative ``path:line`` for a handler.

    Renders the handler's source file relative to the current working
    directory (the operator's repo root) so the error message never leaks the
    operator's absolute home-directory layout to a client error-tracking SaaS.
    """
    try:
        source_file = inspect.getsourcefile(func) or inspect.getfile(func)
    except (TypeError, OSError):
        return getattr(func, "__qualname__", repr(func))
    try:
        _, line = inspect.getsourcelines(func)
    except (OSError, TypeError):
        line = 0
    try:
        rel = os.path.relpath(source_file, os.getcwd())
    except ValueError:
        # Different drive on Windows — fall back to the basename only (still
        # never the absolute path).
        rel = os.path.basename(source_file)
    # If relpath escaped upward past cwd, prefer the basename over a
    # ``../../..`` chain that could still hint at the layout.
    if rel.startswith(".."):
        rel = os.path.basename(source_file)
    return f"{rel}:{line}"


def _module_uses_pep563(func: Callable) -> bool:
    """True iff the handler's module compiled under PEP 563 string annotations.

    The PEP 563 annotations future-import sets the ``CO_FUTURE_ANNOTATIONS``
    compiler flag on every code object in the module, so the function's own
    ``__code__.co_flags`` carries it. Checking the compiler flag (rather than
    inferring from string-shaped annotations) distinguishes genuine PEP 563
    from a legitimate string-literal forward-ref annotation in a non-PEP-563
    module.
    """
    flag = getattr(__future__.annotations, "compiler_flag", 0)
    code = getattr(func, "__code__", None)
    if code is None:
        return False
    return bool(code.co_flags & flag)


def _detect_pep563(func: Callable) -> Dict[str, Any]:
    """Resolve ``func``'s annotations to real types, raising LOUD on PEP 563.

    The resolver classifies parameters by their real (non-string) annotation
    values. When the handler's module enabled the PEP 563 annotations
    future-import, every annotation is a string and the resolver cannot
    distinguish a ``Request`` extractor from a flat ``str`` — so it MUST raise
    at registration (spec §297-313), citing the WORKSPACE-RELATIVE file:line
    (never an absolute ``/Users/...`` path — PII hygiene §313).

    Returns the resolved-hints mapping (name -> type) on the clean path.
    """
    _future_import = "from " + "__future__ import annotations"
    if _module_uses_pep563(func):
        location = _relative_handler_location(func)
        raise ExtractorPEP563Error(
            f"handler at {location} uses '{_future_import}' (PEP 563), which "
            f"stringifies annotations and defeats extractor type resolution; "
            f"remove that future-import from the handler's module. See "
            f"docs/migration-fastapi.md §8."
        )

    try:
        hints = get_type_hints(func, globalns=getattr(func, "__globals__", None))
    except Exception as exc:  # NameError / unresolved forward ref
        location = _relative_handler_location(func)
        raise ExtractorPEP563Error(
            f"handler at {location} has an annotation the resolver could not "
            f"resolve to a real type ({type(exc).__name__}); if the module "
            f"enabled '{_future_import}' (PEP 563), remove it. See "
            f"docs/migration-fastapi.md §8."
        ) from exc

    return hints


def _classify_parameters(func: Callable) -> "List[_ParamSpec]":
    """Introspect ``func`` and classify each parameter.

    Resolves annotations once (raising :class:`ExtractorPEP563Error` on PEP
    563) and produces an ordered list of :class:`_ParamSpec`.
    """
    hints = _detect_pep563(func)
    sig = inspect.signature(func)
    specs: List[_ParamSpec] = []
    for name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            # *args / **kwargs are not extractor-eligible; the handler receives
            # whatever flat kwargs survive filtering.
            continue

        default = param.default
        annotation = hints.get(name, param.annotation)

        if isinstance(default, Depends):
            specs.append(_ParamSpec(name=name, kind=_KIND_DEPENDS, depends=default))
            continue

        # Annotation-driven extractors.
        if annotation is Request or (
            isinstance(annotation, type) and issubclass(annotation, Request)
        ):
            specs.append(_ParamSpec(name=name, kind=_KIND_REQUEST))
            continue
        if annotation is Headers or (
            isinstance(annotation, type) and issubclass(annotation, Headers)
        ):
            specs.append(_ParamSpec(name=name, kind=_KIND_HEADERS))
            continue
        if annotation is Bytes or (
            isinstance(annotation, type) and issubclass(annotation, Bytes)
        ):
            specs.append(_ParamSpec(name=name, kind=_KIND_BYTES))
            continue

        # Everything else is a flat input — same semantics as register_handler.
        specs.append(
            _ParamSpec(
                name=name,
                kind=_KIND_FLAT,
                has_default=param.default is not inspect.Parameter.empty,
                default=(
                    param.default
                    if param.default is not inspect.Parameter.empty
                    else None
                ),
                annotation=(
                    annotation if annotation is not inspect.Parameter.empty else str
                ),
            )
        )
    return specs


class _ParamSpec:
    """Resolved classification of a single handler parameter."""

    __slots__ = (
        "name",
        "kind",
        "depends",
        "has_default",
        "default",
        "annotation",
    )

    def __init__(
        self,
        name: str,
        kind: str,
        depends: Optional[Depends] = None,
        has_default: bool = False,
        default: Any = None,
        annotation: Any = str,
    ) -> None:
        self.name = name
        self.kind = kind
        self.depends = depends
        self.has_default = has_default
        self.default = default
        self.annotation = annotation


class ResolverChain:
    """Per-handler chain that resolves extractor params then dispatches.

    Built once at registration (``build_resolver_chain``); ``resolve_and_call``
    runs once per invocation. The chain memoises ``Depends`` results within a
    single invocation so the same dependency callable referenced by two
    parameters resolves a single time.
    """

    def __init__(self, func: Callable, specs: "List[_ParamSpec]") -> None:
        self._func = func
        self._specs = specs
        self._flat_specs = [s for s in specs if s.kind == _KIND_FLAT]
        self._is_async = inspect.iscoroutinefunction(func)

    @property
    def flat_param_names(self) -> List[str]:
        """Names of the parameters the gateway maps HTTP inputs to."""
        return [s.name for s in self._flat_specs]

    async def _resolve_dependency(
        self,
        depends: Depends,
        request: Optional[Request],
        cache: Dict[Callable, Any],
        overrides: Optional[Dict[Callable, Callable]],
    ) -> Any:
        """Resolve a single ``Depends`` callable (memoised, recursive).

        The ``cache`` is per-invocation so two parameters depending on the same
        callable resolve once. The wrapped callable may itself take extractors
        (``Request`` / nested ``Depends``) — resolved recursively here.

        ``overrides`` is the Shard-2 ``dependency_overrides`` consult-point.
        """
        real = depends.dependency
        if real in cache:
            return cache[real]

        # Shard 2 wires dependency_overrides consult here — when a real->mock
        # override is registered, the mock callable is resolved in place of the
        # real one. Shard 1 invokes the (possibly overridden) callable directly.
        target = real
        if overrides is not None and real in overrides:
            target = overrides[real]

        kwargs = await self._resolve_callable_kwargs(target, request, cache, overrides)
        result = target(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        cache[real] = result
        return result

    async def _resolve_callable_kwargs(
        self,
        callable_: Callable,
        request: Optional[Request],
        cache: Dict[Callable, Any],
        overrides: Optional[Dict[Callable, Callable]],
    ) -> Dict[str, Any]:
        """Build the kwargs for a dependency callable from its own signature.

        A dependency callable may take ``Request`` and/or nested ``Depends``
        parameters; flat parameters with no extractor meaning are left to their
        defaults (a dependency callable is not fed HTTP-body inputs).
        """
        specs = _classify_parameters(callable_)
        kwargs: Dict[str, Any] = {}
        for spec in specs:
            if spec.kind == _KIND_REQUEST:
                kwargs[spec.name] = request
            elif spec.kind == _KIND_HEADERS:
                kwargs[spec.name] = _headers_from_request(request)
            elif spec.kind == _KIND_DEPENDS:
                kwargs[spec.name] = await self._resolve_dependency(
                    spec.depends, request, cache, overrides
                )
            # FLAT params of a dependency callable: only forward when the
            # callable declared a default-less required flat param we cannot
            # satisfy, leave it out so the callable's own default applies.
            elif spec.kind == _KIND_FLAT and not spec.has_default:
                # No source for a required flat param on a dependency callable;
                # surface the canonical INTERNAL_ERROR envelope WITH a
                # correlation id (spec §139) so the operator can look the
                # failure up in the server log — never an opaque TypeError.
                logger.error(
                    "resolver.dependency_flat_param_unsatisfiable",
                    extra={
                        "callable": getattr(callable_, "__qualname__", repr(callable_)),
                        "param": spec.name,
                    },
                )
                raise _internal_error_for(
                    RuntimeError(
                        f"dependency callable requires flat param "
                        f"{spec.name!r} with no source"
                    )
                )
        return kwargs

    async def resolve_and_call(
        self,
        flat_inputs: Dict[str, Any],
        overrides: Optional[Dict[Callable, Callable]] = None,
    ) -> Any:
        """Resolve extractors and invoke the handler.

        ``flat_inputs`` are the gateway-mapped HTTP inputs (only the flat
        params). Extractor params are resolved here. Returns the handler's
        result (normalised by the HandlerNode wrapper).
        """
        request = get_current_request()
        cache: Dict[Callable, Any] = {}
        call_kwargs: Dict[str, Any] = {}

        for spec in self._specs:
            if spec.kind == _KIND_FLAT:
                if spec.name in flat_inputs:
                    call_kwargs[spec.name] = flat_inputs[spec.name]
                elif spec.has_default:
                    call_kwargs[spec.name] = spec.default
                # else: required flat param missing -> let the handler raise the
                # normal MissingParam error path (do not synthesise).
            elif spec.kind == _KIND_REQUEST:
                call_kwargs[spec.name] = request
            elif spec.kind == _KIND_HEADERS:
                call_kwargs[spec.name] = _headers_from_request(request)
            elif spec.kind == _KIND_BYTES:
                call_kwargs[spec.name] = await _bytes_from_request(request)
            elif spec.kind == _KIND_DEPENDS:
                try:
                    call_kwargs[spec.name] = await self._resolve_dependency(
                        spec.depends, request, cache, overrides
                    )
                except NexusHandlerError:
                    # Typed status: surface as-is (the caller maps it).
                    raise
                except Exception as exc:
                    _log_resolver_failure(self._func, spec.depends, exc)
                    raise _internal_error_for(exc) from exc

        result = self._func(**call_kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result


def _headers_from_request(request: Optional[Request]) -> Headers:
    """Build the Nexus Headers mapping from a Starlette request.

    Returns an empty Headers when no request is bound (non-HTTP transports /
    out-of-request resolution).

    Routes through ``Headers.from_pairs`` with the configured
    ``max_request_header_bytes`` cap (stamped on the request by
    ``RequestCaptureMiddleware``) so the 64 KiB early-reject -> HTTP 431 path
    fires on the live resolver surface (spec §87). The plain ``Headers(items)``
    constructor bypasses the cap and is reserved for the no-request empty case.
    """
    if request is None:
        return Headers([])
    items = list(request.headers.items())
    cap = getattr(request, "_nexus_max_request_header_bytes", None)
    if cap is None:
        cap = Headers.DEFAULT_MAX_REQUEST_HEADER_BYTES
    return Headers.from_pairs(items, max_request_header_bytes=cap)


async def _bytes_from_request(request: Optional[Request]) -> Bytes:
    """Read the full request body as a Bytes value, honouring the size cap.

    Short-circuits with HTTP 413 when ``Content-Length`` declares over the cap.
    Log hygiene: only the length is logged, never the body bytes.
    """
    from nexus.extractors import _BodyTooLargeError

    if request is None:
        return Bytes(b"")
    cap = getattr(request, "_nexus_max_request_body_bytes", None)
    if cap is None:
        cap = Bytes.DEFAULT_MAX_REQUEST_BODY_BYTES

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > cap:
            raise _BodyTooLargeError()

    # Accumulate via the stream so the cap bounds MEMORY on the chunked /
    # no-Content-Length path: reject as soon as the running total exceeds the
    # cap rather than buffering the whole (attacker-controlled) body first.
    # Peak memory is <= cap + one chunk (spec §93).
    total = 0
    chunks: List[bytes] = []
    async for chunk in request.stream():
        if not chunk:
            continue
        total += len(chunk)
        if total > cap:
            raise _BodyTooLargeError()
        chunks.append(chunk)
    body = b"".join(chunks)
    logger.debug("bytes_extractor.body_read", extra={"body_length": len(body)})
    return Bytes(body)


def _log_resolver_failure(func: Callable, depends: Depends, exc: Exception) -> None:
    """Log the full server-side context of a resolver dependency failure.

    Per the split-visibility contract (spec §138): exception type, full
    traceback, handler name, dependency __qualname__. The client never sees any
    of this — only the correlation id surfaced in the 500 envelope.
    """
    logger.error(
        "resolver.dependency_failed",
        exc_info=exc,
        extra={
            "handler": getattr(func, "__qualname__", repr(func)),
            "dependency": getattr(
                depends.dependency, "__qualname__", repr(depends.dependency)
            ),
            "exc_type": type(exc).__name__,
        },
    )


def _internal_error_for(exc: Exception) -> NexusHandlerError:
    """Build the client-visible INTERNAL_ERROR envelope with a correlation id.

    BLOCKED in the body (spec §140): str(exc), class name, traceback, request
    echoes, paths, env values. ONLY the canonical shape + a correlation uuid.
    """
    correlation_id = str(uuid.uuid4())
    logger.error("resolver.correlation", extra={"correlation_id": correlation_id})
    return NexusHandlerError(
        status_code=500,
        body={
            "error": "internal error",
            "code": "INTERNAL_ERROR",
            "correlation_id": correlation_id,
        },
    )


def build_resolver_chain(func: Callable) -> ResolverChain:
    """Build a ``ResolverChain`` for ``func`` at registration time.

    Raises :class:`ExtractorPEP563Error` LOUD when the handler's module enabled
    the PEP 563 annotations future-import.
    """
    specs = _classify_parameters(func)
    return ResolverChain(func, specs)
