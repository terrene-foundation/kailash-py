# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed registration guard for reverse-proxy workflow routes.

Issue #2025. Two independent surfaces registered an **unauthenticated**
catch-all reverse proxy:

* ``kailash.servers.WorkflowServer.proxy_workflow``  -> ``/workflows/{name}/{path:path}``
* ``kailash.api.WorkflowAPIGateway.proxy_workflow``  -> ``/{name}/{path:path}``

Both forwarded an arbitrary method, path, and query string to a proxied backend
and returned the body to the caller. Where the backend is an internal service --
the usual reason to configure a proxy at all -- that is an authentication bypass
onto the backend's entire surface, and ``WorkflowServer`` compounded it by
stripping ``Authorization`` on forward so the backend could not re-authorize
either.

CodeQL surfaced this as ``py/partial-ssrf``. That framing is wrong: the scheme,
host, and port come from the developer-supplied ``proxy_url`` at registration
time and ``path`` lands in the path component, so no authority pivot is
constructible. The severity is right; the mechanism is the **missing auth
gate**, which is what this module closes.

Per ``rules/security.md`` § Enforcement-Surface Parity both surfaces MUST learn
the gate together, through ONE shared implementation -- hence this module rather
than a fix in either server. Per ``rules/security.md`` § Secure-Default the gate
**fails closed**: registration raises unless the caller supplies a real
authentication control, matching the precedent set for
``Nexus(enable_auth=True)`` (#2013 / PR #2054) and ``APIGateway(enable_auth=True)``
(#636), both of which now refuse to construct rather than silently serve an open
API.

The four registration-time controls:

1. **Authentication** -- :func:`resolve_proxy_auth_dependency` returns the
   FastAPI dependency to attach to the route, or raises
   :class:`ProxyAuthNotConfiguredError`.
2. **Path allowlist** -- :func:`compile_path_allowlist` +
   :func:`path_matches_allowlist` replace the unbounded ``{path:path}``
   catch-all. ``["*"]`` restores the old behaviour, but only when written
   down explicitly.
3. **Method allowlist** -- :func:`normalize_allowed_methods` defaults to
   ``["GET"]`` rather than every verb.
4. **Traversal rejection** -- :func:`reject_unsafe_proxy_path` refuses ``..``
   segments and encoded separators before the target URL is built, rather
   than relying on the HTTP client's URL normalization.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Iterable, Optional, Sequence, Union

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_ALLOWED_METHODS",
    "PROXY_SUPPORTED_METHODS",
    "PathPattern",
    "ProxyAuthNotConfiguredError",
    "compile_path_allowlist",
    "normalize_allowed_methods",
    "path_matches_allowlist",
    "reject_unsafe_proxy_path",
    "resolve_proxy_auth_dependency",
]

#: Every HTTP method a proxy registration may forward.
PROXY_SUPPORTED_METHODS: tuple[str, ...] = (
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "PATCH",
    "HEAD",
    "OPTIONS",
)

#: Methods forwarded when a registration does not name any. Read-only by
#: default -- a proxy that also writes to the backend must say so.
DEFAULT_ALLOWED_METHODS: tuple[str, ...] = ("GET",)

#: A compiled allowlist entry accepts either a string pattern or a regex.
PathPattern = Union[str, re.Pattern]


class ProxyAuthNotConfiguredError(RuntimeError):
    """Raised when a proxy route would be registered with no authentication.

    This is the fail-closed half of issue #2025. It fires at **registration**
    time (``proxy_workflow(...)``), not at request time, so the failure lands
    in the deployment that misconfigured the proxy rather than silently
    exposing the backend to every caller.
    """


def _auth_error_message(surface: str, name: str) -> str:
    """Build the actionable message naming every accepted wiring."""
    return (
        f"Refusing to register unauthenticated proxy route for workflow "
        f"'{name}' on {surface}. A proxy route forwards arbitrary requests to "
        f"the backend at the registered URL, so registering one without an "
        f"authentication control publishes that backend to every caller "
        f"(issue #2025).\n"
        f"Supply exactly one of:\n"
        f"  - proxy_workflow(..., auth_dependency=<callable>) -- any FastAPI "
        f"dependency that raises HTTPException(401/403) for unauthenticated "
        f"callers;\n"
        f"  - an auth manager on the server: "
        f"WorkflowServer(auth_manager=...) / server.set_auth_manager(...) / "
        f"WorkflowAPIGateway(auth_manager=...), where the manager exposes "
        f"get_current_user_dependency() -- "
        f"kailash.middleware.auth.MiddlewareAuthManager is the shipped "
        f"implementation;\n"
        f"  - server.declare_external_auth('<reason>') when an ASGI "
        f"middleware you installed on this app already authenticates every "
        f"request (for example nexus.auth.jwt.JWTMiddleware, installed by "
        f"Nexus(enable_auth=True)). This records an explicit, logged "
        f"acknowledgement -- it does not install anything."
    )


def resolve_proxy_auth_dependency(
    *,
    name: str,
    surface: str,
    auth_dependency: Optional[Callable[..., Any]] = None,
    auth_manager: Any = None,
    external_auth_reason: Optional[str] = None,
) -> Optional[Callable[..., Any]]:
    """Resolve the authentication dependency for a proxy route, or refuse.

    Resolution order, most specific first:

    1. ``auth_dependency`` -- attached to the route verbatim.
    2. ``auth_manager`` -- ``auth_manager.get_current_user_dependency()`` is
       called and its return value attached.
    3. ``external_auth_reason`` -- the caller has explicitly declared that an
       ASGI middleware outside this class authenticates the app. Returns
       ``None`` (no route dependency) after logging a WARNING.
    4. Nothing -- :class:`ProxyAuthNotConfiguredError`.

    Args:
        name: Workflow identifier being registered, for the error message.
        surface: Human-readable name of the registering class, for the message.
        auth_dependency: An explicit FastAPI dependency callable.
        auth_manager: An object exposing ``get_current_user_dependency()``.
        external_auth_reason: Non-empty justification recorded by
            ``declare_external_auth``.

    Returns:
        The dependency callable to attach to the route, or ``None`` when
        authentication is enforced by externally-declared middleware.

    Raises:
        ProxyAuthNotConfiguredError: When no authentication source is
            configured, or when ``auth_manager`` does not expose a usable
            ``get_current_user_dependency()``.
    """
    if auth_dependency is not None:
        if not callable(auth_dependency):
            raise ProxyAuthNotConfiguredError(
                f"auth_dependency for proxied workflow '{name}' is not "
                f"callable (got {type(auth_dependency).__name__}). FastAPI "
                f"dependencies must be callables."
            )
        return auth_dependency

    if auth_manager is not None:
        # Fail-CLOSED probe. A `hasattr` guard whose False branch silently
        # continues is the exact shape that shipped `enable_auth=True` as a
        # no-op for two releases (#2013, `zero-tolerance.md` Rule 3d): the
        # probed name had zero definitions anywhere, so the install never ran
        # and nothing said so. Here the absent branch RAISES, so a manager
        # that cannot produce a dependency stops the registration instead of
        # quietly leaving the route open.
        factory = getattr(auth_manager, "get_current_user_dependency", None)
        if not callable(factory):
            raise ProxyAuthNotConfiguredError(
                f"auth_manager supplied for proxied workflow '{name}' "
                f"({type(auth_manager).__name__}) does not expose a callable "
                f"get_current_user_dependency(); it cannot authenticate the "
                f"proxy route. kailash.middleware.auth.MiddlewareAuthManager "
                f"is the shipped implementation of that contract."
            )
        dependency = factory()
        if not callable(dependency):
            raise ProxyAuthNotConfiguredError(
                f"auth_manager.get_current_user_dependency() for proxied "
                f"workflow '{name}' returned "
                f"{type(dependency).__name__}, which is not callable and "
                f"cannot be used as a FastAPI dependency."
            )
        return dependency

    if external_auth_reason:
        logger.warning(
            "proxy_guard.external_auth_declared",
            extra={
                "workflow": name,
                "surface": surface,
                "reason": external_auth_reason,
            },
        )
        logger.warning(
            "Proxied workflow '%s' registered on %s with NO route-level "
            "authentication; the deployment declared that an external ASGI "
            "middleware authenticates every request. Reason: %s. If that "
            "middleware is ever removed or misconfigured this route forwards "
            "unauthenticated requests to the backend (issue #2025).",
            name,
            surface,
            external_auth_reason,
        )
        return None

    raise ProxyAuthNotConfiguredError(_auth_error_message(surface, name))


def normalize_allowed_methods(
    methods: Optional[Sequence[str]],
    *,
    name: str,
    supported: Sequence[str] = PROXY_SUPPORTED_METHODS,
) -> list[str]:
    """Validate and normalize a per-registration HTTP method allowlist.

    Args:
        methods: Requested methods. ``None`` selects
            :data:`DEFAULT_ALLOWED_METHODS` (``["GET"]``).
        name: Workflow identifier, for error messages.
        supported: Methods this surface is able to forward.

    Returns:
        Upper-cased methods, de-duplicated, in ``supported`` order so the
        registered route is stable regardless of caller ordering.

    Raises:
        ValueError: When the allowlist is empty or names an unsupported method.
    """
    if methods is None:
        methods = DEFAULT_ALLOWED_METHODS

    if isinstance(methods, str):
        raise ValueError(
            f"allowed_methods for proxied workflow '{name}' must be a "
            f"sequence of method names, not a bare string "
            f"({methods!r}). Pass e.g. ['GET'] or ['GET', 'POST']."
        )

    requested = [m.strip().upper() for m in methods if m and m.strip()]
    if not requested:
        raise ValueError(
            f"allowed_methods for proxied workflow '{name}' is empty. A proxy "
            f"registration must name at least one forwardable method; the "
            f"default is ['GET']."
        )

    supported_upper = [m.upper() for m in supported]
    unsupported = sorted({m for m in requested if m not in supported_upper})
    if unsupported:
        raise ValueError(
            f"allowed_methods for proxied workflow '{name}' names "
            f"unsupported method(s) {unsupported}. Supported: "
            f"{list(supported_upper)}."
        )

    return [m for m in supported_upper if m in set(requested)]


def compile_path_allowlist(
    patterns: Optional[Iterable[PathPattern]],
    *,
    name: str,
) -> list[PathPattern]:
    """Validate a path allowlist supplied at proxy registration.

    Replaces the unbounded ``{path:path}`` catch-all with an explicit set of
    forwardable paths. String patterns are matched against the forwarded path
    with the leading ``/`` stripped from both sides:

    * ``"*"`` -- every path. This restores the pre-#2025 behaviour and is
      accepted, but only when the deployment writes it down.
    * ``"api/*"`` -- ``api`` and anything beneath it, at any depth.
    * ``"status"`` -- that exact path and nothing else.

    A compiled :class:`re.Pattern` is matched with ``fullmatch`` against the
    same normalized path, for allowlists a prefix cannot express.

    Args:
        patterns: The allowlist. ``None`` or empty raises -- there is no
            implicit default, because the only safe implicit default would be
            "deny everything", which silently breaks the proxy, and the only
            convenient one is the catch-all this rule exists to remove.
        name: Workflow identifier, for error messages.

    Returns:
        The normalized allowlist, ready for :func:`path_matches_allowlist`.

    Raises:
        ValueError: When the allowlist is missing, empty, or holds an entry
            that is neither a string nor a compiled regex.
    """
    if patterns is None:
        raise ValueError(
            f"allowed_paths is required when registering proxied workflow "
            f"'{name}'. Before issue #2025 this route forwarded EVERY path "
            f"beneath it to the backend; that catch-all is now explicit. "
            f"Pass the paths the backend should expose, e.g. "
            f"allowed_paths=['execute', 'status'] or allowed_paths=['api/*'], "
            f"or allowed_paths=['*'] to keep forwarding every path."
        )

    if isinstance(patterns, (str, re.Pattern)):
        raise ValueError(
            f"allowed_paths for proxied workflow '{name}' must be a sequence "
            f"of patterns, not a single {type(patterns).__name__} "
            f"({patterns!r}). Wrap it in a list: [{patterns!r}]."
        )

    compiled: list[PathPattern] = []
    for pattern in patterns:
        if isinstance(pattern, re.Pattern):
            compiled.append(pattern)
            continue
        if not isinstance(pattern, str):
            raise ValueError(
                f"allowed_paths for proxied workflow '{name}' holds a "
                f"{type(pattern).__name__} ({pattern!r}); entries must be "
                f"strings or compiled regular expressions."
            )
        normalized = pattern.strip().lstrip("/")
        if not normalized:
            raise ValueError(
                f"allowed_paths for proxied workflow '{name}' holds an empty "
                f"pattern ({pattern!r}). Use '*' if every path should be "
                f"forwarded."
            )
        compiled.append(normalized)

    if not compiled:
        raise ValueError(
            f"allowed_paths for proxied workflow '{name}' is empty. A proxy "
            f"registration must name at least one forwardable path; use "
            f"allowed_paths=['*'] to forward every path."
        )

    return compiled


def path_matches_allowlist(path: str, allowlist: Sequence[PathPattern]) -> bool:
    """Return True when ``path`` is forwardable under ``allowlist``.

    Args:
        path: The path captured by the route, with or without a leading ``/``.
        allowlist: The value returned by :func:`compile_path_allowlist`.

    Returns:
        True if any entry matches. An empty allowlist matches nothing --
        deny-by-default, so a construction bug cannot open the route.
    """
    candidate = path.lstrip("/")
    for entry in allowlist:
        if isinstance(entry, re.Pattern):
            if entry.fullmatch(candidate):
                return True
            continue
        if entry == "*":
            return True
        if entry.endswith("/*"):
            prefix = entry[:-2]
            if candidate == prefix or candidate.startswith(prefix + "/"):
                return True
            continue
        if entry.endswith("*"):
            if candidate.startswith(entry[:-1]):
                return True
            continue
        if candidate == entry:
            return True
    return False


#: Percent-encoded separators and dot-segments. Starlette decodes a path
#: parameter once, so a singly-encoded ``%2e%2e`` already arrives as ``..``
#: and is caught by the segment check below. These catch the DOUBLE-encoded
#: form (``%252e%252e`` -> ``%2e%2e`` after Starlette's decode), which this
#: process would forward verbatim for the backend to decode a second time.
_ENCODED_TRAVERSAL_TOKENS: tuple[str, ...] = ("%2e", "%2f", "%5c")


def reject_unsafe_proxy_path(path: str) -> Optional[str]:
    """Return a human-readable reason to refuse ``path``, or ``None``.

    Checked **before** the target URL is built, rather than relying on the
    HTTP client's URL normalization to collapse ``..`` -- ``yarl`` and
    ``httpx`` normalize differently, and neither is a security control.

    Args:
        path: The raw path captured by the proxy route.

    Returns:
        The refusal reason, or ``None`` when the path is safe to forward.
    """
    if "\x00" in path:
        return "path contains a null byte"
    for char in path:
        if ord(char) < 0x20 or ord(char) == 0x7F:
            return "path contains a control character"
    if "\\" in path:
        return "path contains a backslash"
    lowered = path.lower()
    for token in _ENCODED_TRAVERSAL_TOKENS:
        if token in lowered:
            return f"path contains an encoded path separator or dot-segment ({token})"
    if any(segment == ".." for segment in path.split("/")):
        return "path contains a parent-directory segment (..)"
    return None
