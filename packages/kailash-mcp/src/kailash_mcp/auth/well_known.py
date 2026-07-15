# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Server-publish half of the OAuth 2.1 protected-resource surface (#1712).

The ``kailash-mcp`` server acts as an OAuth 2.1 **resource server**. Per the MCP
2025-11-25 authorization spec it MUST publish RFC 9728 *Protected Resource
Metadata* (PRM) and MUST challenge unauthenticated requests with an RFC 9110
§11.6.1 ``WWW-Authenticate: Bearer`` header pointing at that metadata. The
CLIENT half (RFC 9728 PRM fetch, RFC 8414/OIDC AS-metadata discovery, PKCE-S256
pre-check) already lives in ``kailash_mcp.auth.oauth.OAuth2Client``; this module
is the SERVER half those clients discover.

This module carries the pure, dependency-free builders (the PRM well-known URL
derivation and the ``WWW-Authenticate`` challenge string) so ``oauth.py`` can
import them without a cycle, plus two mountable route surfaces for the live
HTTP/SSE transport:

* :func:`create_protected_resource_metadata_app` — a pure ASGI 3.0 application
  serving ``GET /.well-known/oauth-protected-resource`` (no framework dep), and
* :func:`build_well_known_routes` — a Starlette ``Route`` list for mounting on
  the FastMCP / SSE Starlette surface (Starlette imported lazily).

The well-known metadata endpoint is intentionally **unauthenticated** — RFC 9728
§3 requires it be publicly fetchable so a client can discover where to obtain a
token before it has one.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from urllib.parse import ParseResult, urlparse

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids Starlette runtime dep
    from starlette.routing import Route

logger = logging.getLogger(__name__)

# RFC 9728 §3.1 — the registered well-known URI suffix for Protected Resource
# Metadata. The served path is this suffix followed by the resource's path
# component (empty for an origin-root resource → the bare well-known path).
WELL_KNOWN_PROTECTED_RESOURCE_SUFFIX = "/.well-known/oauth-protected-resource"


def _require_absolute_resource_url(resource_uri: str) -> ParseResult:
    """Parse + validate ``resource_uri`` as an absolute http(s) URL.

    RFC 9728 §3.1 derives the PRM well-known URL from the resource identifier,
    whose path component is spliced after the well-known suffix. A NON-URL
    identifier (a bare token such as ``"mcp-api"``) has no scheme/host and its
    ``urlparse().path`` carries no leading ``/`` — deriving a PRM URL from it
    yields a corrupt string (``":///.well-known/oauth-protected-resourcemcp-api"``)
    that no RFC 9728 client can fetch. Reject it fail-loud (defense in depth for
    ``ResourceServer.__init__``'s own guard) rather than emit a broken doc.
    """
    parsed = urlparse(resource_uri)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"RFC 9728 protected-resource identifier must be an absolute "
            f"http(s) URL (scheme http/https + non-empty host); got "
            f'{resource_uri!r}. Pass resource="https://<host>/<path>".'
        )
    return parsed


def protected_resource_metadata_path(resource_uri: str) -> str:
    """Return the request path a client fetches PRM from for ``resource_uri``.

    Per RFC 9728 §3.1 the ``/.well-known/oauth-protected-resource`` segment is
    inserted between the origin and the resource's path. For an origin-root
    resource (``https://srv.example.com``) this is exactly the well-known
    suffix; for a path-bearing resource (``https://srv.example.com/mcp``) the
    resource path is appended (``/.well-known/oauth-protected-resource/mcp``).

    A validated URL's ``path`` is empty (origin-root) or begins with ``/``, so
    the composition below always carries the correct ``/`` separator; a non-URL
    ``resource_uri`` is rejected fail-loud by :func:`_require_absolute_resource_url`.

    This mirrors ``OAuth2Client._wellknown_prm_url`` on the client side so the
    path the server serves is byte-identical to the one the client derives.
    """
    path = _require_absolute_resource_url(resource_uri).path.rstrip("/")
    return f"{WELL_KNOWN_PROTECTED_RESOURCE_SUFFIX}{path}"


def protected_resource_metadata_url(resource_uri: str) -> str:
    """Return the absolute RFC 9728 PRM URL for ``resource_uri``.

    ``https://srv.example.com/mcp`` →
    ``https://srv.example.com/.well-known/oauth-protected-resource/mcp``.

    Raises ``ValueError`` (via :func:`_require_absolute_resource_url`) when
    ``resource_uri`` is not an absolute http(s) URL.
    """
    parsed = _require_absolute_resource_url(resource_uri)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return f"{origin}{protected_resource_metadata_path(resource_uri)}"


def build_www_authenticate_challenge(
    *,
    resource_metadata_url: str,
    scope: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> str:
    """Build an RFC 9110 §11.6.1 ``WWW-Authenticate: Bearer`` challenge value.

    Emits the quoted ``key="value"`` auth-param form that
    ``kailash_mcp.auth.oauth.parse_www_authenticate`` parses — the two are
    inverse operations sharing one param shape. ``resource_metadata`` (RFC 9728
    §5.1) points a challenged client at this resource server's PRM document;
    ``scope`` (RFC 6750 §3) advertises the scope the caller lacked; ``error`` /
    ``error_description`` (RFC 6750 §3) classify the failure.

    Args:
        resource_metadata_url: Absolute RFC 9728 PRM URL for this resource.
        scope: Space-delimited required scope(s), if any.
        error: RFC 6750 error code (``invalid_token`` / ``invalid_request`` /
            ``insufficient_scope``), if the challenge follows a failed auth.
        error_description: Human-readable RFC 6750 error description.

    Returns:
        The ``WWW-Authenticate`` header VALUE, e.g.
        ``Bearer resource_metadata="https://…", scope="mcp"``.
    """
    # A double quote would break the RFC 9110 quoted-string parse (the
    # parse_www_authenticate regex stops at the first '"'); reject it fail-loud
    # rather than emit a corrupt, silently-truncating header.
    params = [("resource_metadata", resource_metadata_url)]
    if error is not None:
        params.append(("error", error))
    if error_description is not None:
        params.append(("error_description", error_description))
    if scope:
        params.append(("scope", scope))

    rendered = []
    for key, value in params:
        if '"' in value:
            raise ValueError(
                f"WWW-Authenticate param {key!r} contains a double quote, which "
                f"would corrupt the RFC 9110 §11.6.1 quoted-string form: {value!r}"
            )
        rendered.append(f'{key}="{value}"')
    return "Bearer " + ", ".join(rendered)


# ---------------------------------------------------------------------------
# Live-transport route surfaces
# ---------------------------------------------------------------------------

# Duck-typed protocol for the object the route surfaces consume: any object
# exposing ``get_protected_resource_metadata() -> dict`` (ResourceServer does).
_MetadataProvider = Any


def create_protected_resource_metadata_app(
    resource_server: _MetadataProvider,
) -> Callable:
    """Build a pure ASGI 3.0 app serving the RFC 9728 PRM document.

    Returns an ``async def app(scope, receive, send)`` callable that answers
    ``GET`` at the resource's PRM path (:func:`protected_resource_metadata_path`)
    with a ``200 application/json`` body of
    ``resource_server.get_protected_resource_metadata()``, and ``404`` for any
    other path/method. No web framework is required — the app mounts on any ASGI
    server (uvicorn, hypercorn, the FastMCP Starlette surface).

    The endpoint is unauthenticated by design (RFC 9728 §3): a client must be
    able to fetch it before it holds a token.
    """
    metadata = resource_server.get_protected_resource_metadata()
    metadata_path = protected_resource_metadata_path(metadata["resource"])
    body = json.dumps(metadata).encode("utf-8")

    async def app(scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":  # pragma: no cover - defensive
            raise ValueError(
                f"protected-resource-metadata app supports only the 'http' ASGI "
                f"scope, got {scope['type']!r}"
            )
        if scope["method"] == "GET" and scope["path"] == metadata_path:
            logger.info(
                "oauth.protected_resource_metadata.serve path=%s resource=%s",
                metadata_path,
                metadata["resource"],
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"public, max-age=3600"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        logger.debug(
            "oauth.protected_resource_metadata.miss method=%s path=%s",
            scope.get("method"),
            scope.get("path"),
        )
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"error":"not_found"}'})

    return app


def build_well_known_routes(resource_server: _MetadataProvider) -> "List[Route]":
    """Build Starlette ``Route``\\ s serving the RFC 9728 PRM document.

    For mounting on the FastMCP / SSE Starlette surface. Starlette is imported
    lazily so ``import kailash_mcp.auth.well_known`` works without it; the import
    raises a descriptive error only if this function is actually called without
    Starlette installed.

    Returns a single-element list: a ``GET`` route at the resource's PRM path
    returning the metadata JSON.
    """
    try:
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route
    except ImportError as exc:  # pragma: no cover - exercised only sans starlette
        raise ImportError(
            "build_well_known_routes requires Starlette (installed with the "
            "FastMCP HTTP/SSE server surface); install kailash-mcp[server]."
        ) from exc

    metadata = resource_server.get_protected_resource_metadata()
    metadata_path = protected_resource_metadata_path(metadata["resource"])

    async def _metadata_endpoint(request: "Request") -> "JSONResponse":
        doc = resource_server.get_protected_resource_metadata()
        logger.info(
            "oauth.protected_resource_metadata.serve path=%s resource=%s",
            metadata_path,
            doc["resource"],
        )
        return JSONResponse(
            doc,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    return [
        Route(
            metadata_path,
            _metadata_endpoint,
            methods=["GET"],
            name="oauth_protected_resource_metadata",
        )
    ]
