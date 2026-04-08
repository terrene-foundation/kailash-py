# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Adapter from fabric route dicts to Nexus / FastAPI handlers (Phase 5.8).

The fabric subsystems (``serving``, ``health``, ``sse``, ``webhooks``)
return route definitions of the shape::

    {
        "method": "GET",
        "path": "/fabric/{product_name}",
        "handler": <async callable>,
        "metadata": {...},
    }

The handler callable follows fabric's internal convention:

- It accepts a FastAPI ``Request`` instance via the ``request`` keyword
  (some handlers don't, in which case we fall back to passing only
  query / path parameters as kwargs).
- It returns a ``dict`` with optional sentinel keys:

  ``_status`` — int HTTP status code (default ``200``)
  ``_headers`` — additional response headers
  ``_stream`` — async generator for streaming responses (SSE)

  Anything else in the dict is the JSON body.

Nexus / FastAPI handlers, in contrast, accept the FastAPI request and
return a ``Response`` (or anything FastAPI can serialise) where the
status code, headers and body are set explicitly. This module provides
:func:`fabric_handler_to_fastapi` which wraps a fabric handler so that
:meth:`Nexus.register_endpoint` can register it directly.

Design notes:

* The adapter is intentionally framework-agnostic about *which*
  exception classes the underlying handler may raise. Any uncaught
  exception is logged and re-raised so FastAPI's normal exception
  handling kicks in (returning 500 with the configured exception
  handler).
* Streaming responses (``_stream``) are detected and routed through
  ``StreamingResponse`` so SSE handlers work end-to-end.
* The adapter is *one-way* — fabric ``stop()`` cannot deregister
  routes from FastAPI's app router today. The runtime tracks the
  registered paths so a future ``unregister_endpoint`` can remove
  them.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

__all__ = [
    "fabric_handler_to_fastapi",
    "register_route_dict",
    "register_route_dicts",
]


def _coerce_handler_call(
    fabric_handler: Callable[..., Awaitable[Any]],
    request: Request,
    path_params: Dict[str, Any],
) -> Awaitable[Any]:
    """Invoke ``fabric_handler`` with the kwargs it accepts.

    Some fabric handlers expect ``request=...`` and the named path
    parameters; others expect only the path parameters. We inspect the
    handler signature to decide which kwargs to pass so we don't trip
    over a ``TypeError`` from an unexpected keyword.
    """
    sig = inspect.signature(fabric_handler)
    accepts_request = "request" in sig.parameters or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    call_kwargs: Dict[str, Any] = dict(path_params)
    if accepts_request:
        call_kwargs["request"] = request
    return fabric_handler(**call_kwargs)


def fabric_handler_to_fastapi(
    fabric_handler: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Wrap a fabric handler so it returns a proper FastAPI response.

    The returned coroutine accepts a FastAPI ``Request`` plus any
    explicit path-parameter kwargs that FastAPI's router will pass.
    It calls the underlying fabric handler, then translates its dict
    response into ``StreamingResponse`` (when ``_stream`` is present)
    or ``JSONResponse`` (otherwise).

    Args:
        fabric_handler: The fabric route handler to wrap.

    Returns:
        An async callable suitable for ``Nexus.register_endpoint``.
    """

    async def adapter(request: Request, **path_params: Any) -> Any:
        try:
            result = await _coerce_handler_call(fabric_handler, request, path_params)
        except Exception:
            logger.exception(
                "fabric.handler.error",
                extra={
                    "handler": getattr(fabric_handler, "__name__", repr(fabric_handler))
                },
            )
            raise

        if not isinstance(result, dict):
            return result

        status_code = int(result.pop("_status", 200))
        headers = result.pop("_headers", None) or {}
        stream = result.pop("_stream", None)

        if stream is not None:
            media_type = headers.get("Content-Type") or "text/event-stream"
            return StreamingResponse(
                stream,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
            )

        # When the dict contains a single ``data`` key (the convention
        # used by health/trace handlers), unwrap it so callers see the
        # payload directly. Otherwise return the dict as-is.
        if set(result.keys()) == {"data"}:
            body: Any = result["data"]
        else:
            body = result
        return JSONResponse(body, status_code=status_code, headers=headers)

    adapter.__name__ = (
        getattr(fabric_handler, "__name__", "fabric_handler") + "_fastapi"
    )
    return adapter


def register_route_dict(nexus: Any, route: Dict[str, Any]) -> Dict[str, Any]:
    """Register a single fabric route dict on a Nexus instance.

    Returns a small descriptor of what was registered so callers can
    keep track for shutdown.
    """
    method = route["method"]
    path = route["path"]
    handler = fabric_handler_to_fastapi(route["handler"])
    nexus.register_endpoint(path, [method], handler)
    return {"path": path, "method": method, "handler_name": handler.__name__}


def register_route_dicts(
    nexus: Any, routes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Register a list of fabric route dicts on a Nexus instance.

    Returns the list of descriptors from :func:`register_route_dict`.
    """
    return [register_route_dict(nexus, r) for r in routes]
