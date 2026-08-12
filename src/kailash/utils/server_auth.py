# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed authentication gate for Kailash HTTP server surfaces.

Issue #2072. On a default ``WorkflowServer`` / ``create_gateway()`` with a
single ``register_workflow(...)`` -- the primary documented use --
``POST /workflows/{name}/execute`` executed the workflow for an **anonymous**
caller. Measured on a real socket, not inferred::

    POST /workflows/probe/execute   -> 200
      body: b'{"outputs":{"n":{"result":{"ran":true}}},"execution_time":6.85,...}'

The workflow did not merely route -- it RAN. ``{"ran": true}`` is the node's
output and ``execution_time`` is real wall-clock. That is server-side code
execution by an unauthenticated caller.

Two INDEPENDENT surfaces carried the defect:

* ``kailash.servers.WorkflowServer``   (and its Durable/Enterprise subclasses)
* ``kailash.api.WorkflowAPIGateway``

Per ``rules/security.md`` § Enforcement-Surface Parity both learn the gate
together, through the ONE shared implementation in this module, rather than
through a fix in either server -- the same structure ``kailash.utils.proxy_guard``
used for the sibling half of this defect class (#2025).

Per ``rules/security.md`` § Secure-Default the gate **fails CLOSED**:
``require_auth`` defaults to ``True`` and construction RAISES when no credential
source is configured. This matches the precedent already set for
``Nexus(enable_auth=True)`` (#2013 / PR #2054) and ``APIGateway(enable_auth=True)``
(#636), both of which refuse to construct rather than silently serve an open API.

**This is a breaking change and is meant to be.** Every deployment it stops was
already serving anonymous workflow execution. The raise does not turn a working
system into an outage; it surfaces a pre-existing exposure at deploy time
instead of leaving it silently in production.

Credentials come from the environment (``rules/env-models.md``: ``.env`` is the
single source of truth):

* ``KAILASH_JWT_SECRET``       -- HS* signing secret, minimum 32 bytes.
* ``KAILASH_JWT_PUBLIC_KEY``   -- PEM public key for RS*/ES* verification.
* ``KAILASH_JWT_ALGORITHM``    -- defaults to ``HS256``.
* ``KAILASH_API_KEY_<NAME>``   -- one or more API keys; enables ``X-API-Key``.
* ``KAILASH_AUTH_EXEMPT_PATHS`` -- comma-separated extra exempt paths.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

if TYPE_CHECKING:  # pragma: no cover -- typing only
    from kailash.trust.auth.jwt import JWTConfig

logger = logging.getLogger(__name__)

__all__ = [
    "API_KEY_ENV_PREFIX",
    "DEFAULT_EXEMPT_PATHS",
    "EXEMPT_PATHS_ENV",
    "InvalidServerAuthSecretError",
    "JWT_ALGORITHM_ENV",
    "JWT_PUBLIC_KEY_ENV",
    "JWT_SECRET_ENV",
    "MIN_SECRET_BYTES",
    "ServerAuthNotConfiguredError",
    "build_server_auth_config",
    "collect_api_keys",
    "install_server_auth_middleware",
    "resolve_server_auth",
]

JWT_SECRET_ENV = "KAILASH_JWT_SECRET"
JWT_PUBLIC_KEY_ENV = "KAILASH_JWT_PUBLIC_KEY"
JWT_ALGORITHM_ENV = "KAILASH_JWT_ALGORITHM"
API_KEY_ENV_PREFIX = "KAILASH_API_KEY_"
EXEMPT_PATHS_ENV = "KAILASH_AUTH_EXEMPT_PATHS"

#: RFC 7518 §3.2 -- an HS256 key MUST be at least as long as the hash output.
#: ``JWTConfig.__post_init__`` enforces the same floor; this constant exists so
#: the message names the number before ``JWTConfig`` is even constructed.
MIN_SECRET_BYTES = 32

#: Liveness/readiness probes must answer without credentials, or every
#: orchestrator marks an authenticated server unhealthy and restarts it.
#:
#: NOTHING else is exempt by default. In particular ``/docs``, ``/openapi.json``,
#: ``/metrics``, ``/dashboard`` and ``/`` are all PROTECTED, because each one
#: describes or exposes the protected surface: ``/`` and ``/workflows``
#: enumerate every registered workflow, ``/metrics`` and ``/dashboard`` report
#: operational state, and the OpenAPI documents hand an anonymous caller the
#: full route map. ``JWTConfig``'s own default exempt list is broader (it
#: exempts ``/docs`` and ``/metrics``) and is deliberately NOT reused here.
DEFAULT_EXEMPT_PATHS: tuple[str, ...] = (
    "/health",
    "/health/*",
    "/enterprise/health",
)


class ServerAuthNotConfiguredError(RuntimeError):
    """``require_auth=True`` with no credential source configured.

    Raised at CONSTRUCTION, not at request time. A server that started and then
    500'd per request would still have advertised itself as healthy to an
    orchestrator; refusing to construct is what makes the exposure visible at
    deploy time.

    Subclasses :class:`RuntimeError` so existing ``except RuntimeError``
    handlers keep working, mirroring the ``APIGateway`` fix for issue #636.
    """


class InvalidServerAuthSecretError(ValueError):
    """A configured signing secret is present but too weak to use."""


def collect_api_keys(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return ``{KAILASH_API_KEY_<NAME>: value}`` for every non-empty API key.

    Args:
        env: Environment mapping to read (defaults to ``os.environ``).

    Returns:
        Mapping of the full environment-variable name to its key value.
    """
    source = os.environ if env is None else env
    return {
        name: value
        for name, value in source.items()
        if name.startswith(API_KEY_ENV_PREFIX) and value
    }


def _make_api_key_validator(api_keys: Dict[str, str]):
    """Build a constant-time API-key validator over the configured keys.

    ``secrets.compare_digest`` is mandatory: a plain ``==`` short-circuits on
    the first differing byte and leaks the key prefix under a remote-timing
    oracle. The loop compares against EVERY configured key rather than
    returning early, so the number of comparisons does not depend on which key
    matched.
    """
    expected = list(api_keys.values())

    def _validate(api_key: str) -> bool:
        matched = False
        for candidate in expected:
            if secrets.compare_digest(api_key, candidate):
                matched = True
        return matched

    return _validate


def _exempt_paths(
    extra: Optional[Sequence[str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Merge built-in, environment-supplied, and caller-supplied exempt paths."""
    source = os.environ if env is None else env
    paths: List[str] = list(DEFAULT_EXEMPT_PATHS)
    raw = source.get(EXEMPT_PATHS_ENV, "")
    paths.extend(p.strip() for p in raw.split(",") if p.strip())
    if extra:
        paths.extend(p.strip() for p in extra if p and p.strip())
    # dict.fromkeys preserves order while removing duplicates.
    return list(dict.fromkeys(paths))


def build_server_auth_config(
    *,
    extra_exempt_paths: Optional[Sequence[str]] = None,
    env: Optional[Dict[str, str]] = None,
    server_label: str = "This server",
) -> "JWTConfig":
    """Build a :class:`JWTConfig` from the environment, or fail loud.

    Args:
        extra_exempt_paths: Paths appended to the built-in exempt list.
        env: Environment mapping to read (defaults to ``os.environ``).
        server_label: Name used in the error message so the operator knows
            which construction call to fix.

    Returns:
        A ``JWTConfig`` with at least one credential source wired.

    Raises:
        ServerAuthNotConfiguredError: No credential source is present.
        InvalidServerAuthSecretError: ``KAILASH_JWT_SECRET`` is present but
            shorter than :data:`MIN_SECRET_BYTES`.
        ImportError: PyJWT is not installed (the ``kailash[trust]`` extra).
    """
    source = os.environ if env is None else env

    # Imported function-locally: kailash.trust.auth.jwt raises ImportError at
    # module scope when PyJWT is absent, and that must surface here -- at
    # construction, with actionable wiring -- rather than at import time of
    # whatever module happened to touch the server package first.
    from kailash.trust.auth.jwt import JWTConfig

    secret = source.get(JWT_SECRET_ENV) or None
    public_key = source.get(JWT_PUBLIC_KEY_ENV) or None
    algorithm = source.get(JWT_ALGORITHM_ENV) or "HS256"
    api_keys = collect_api_keys(source)

    if not (secret or public_key or api_keys):
        raise ServerAuthNotConfiguredError(
            f"{server_label} requires authentication (require_auth=True) but no "
            "credential source is configured, so no authentication could be "
            "installed. Refusing to start an unauthenticated server: without a "
            "gate, POST /workflows/{name}/execute runs arbitrary registered "
            "workflows for anonymous callers (issue #2072).\n"
            "Set one of:\n"
            f"  {JWT_SECRET_ENV}=<at least {MIN_SECRET_BYTES} bytes>   "
            "(HS256 bearer tokens)\n"
            f"  {JWT_PUBLIC_KEY_ENV}=<PEM public key>          "
            f"(with {JWT_ALGORITHM_ENV}=RS256/ES256)\n"
            f"  {API_KEY_ENV_PREFIX}<NAME>=<key>                 "
            "(X-API-Key header)\n"
            "Or pass an explicit JWTConfig as auth_config=...\n"
            "Or, to run WITHOUT authentication, say so explicitly with "
            "require_auth=False.\n"
            "If an ASGI middleware outside this server already authenticates "
            "every request, declare it with "
            "external_auth_reason='<what provides it>'."
        )

    if secret is not None and len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise InvalidServerAuthSecretError(
            f"{JWT_SECRET_ENV} must be at least {MIN_SECRET_BYTES} bytes "
            f"(got {len(secret.encode('utf-8'))}). A short HS256 key is "
            "brute-forceable; see RFC 7518 §3.2."
        )

    if secret is None and public_key is None:
        # API-key-only deployment. JWTConfig.__post_init__ rejects a symmetric
        # algorithm with no secret, so the bearer arm needs SOME key -- and the
        # fail-CLOSED choice is a fresh random one that is never written down
        # or returned. No party can mint a token against it, so every Bearer
        # request is rejected while the X-API-Key arm works. A fixed or empty
        # secret here would forge-enable the whole JWT path.
        secret = secrets.token_urlsafe(48)
        logger.info(
            "server_auth.bearer_disabled_api_key_only",
            extra={"reason": "no JWT credential configured"},
        )

    config = JWTConfig(
        secret=secret,
        public_key=public_key,
        algorithm=algorithm,
        exempt_paths=_exempt_paths(extra_exempt_paths, env=source),
        api_key_enabled=bool(api_keys),
        api_key_validator=_make_api_key_validator(api_keys) if api_keys else None,
    )

    # Booleans and counts only -- never the secret, the key, or any API key.
    logger.info(
        "server_auth.configured",
        extra={
            "jwt_secret": bool(source.get(JWT_SECRET_ENV)),
            "public_key": bool(public_key),
            "algorithm": algorithm,
            "api_keys": len(api_keys),
            "exempt_paths": len(config.exempt_paths),
        },
    )
    return config


def resolve_server_auth(
    *,
    require_auth: bool,
    auth_config: Any = None,
    external_auth_reason: Optional[str] = None,
    extra_exempt_paths: Optional[Sequence[str]] = None,
    server_label: str = "This server",
    env: Optional[Dict[str, str]] = None,
) -> Optional["JWTConfig"]:
    """Decide what authentication to install, failing closed.

    Resolution order:

    1. ``external_auth_reason`` -- a non-empty string declares that an ASGI
       middleware OUTSIDE this server authenticates every request. Returns
       ``None`` (install nothing). This is how Nexus, which installs its own
       ``nexus.auth.jwt.JWTMiddleware``, avoids a duplicate layer.
    2. ``require_auth=False`` -- an explicit opt-out. Returns ``None`` and
       emits a loud WARN naming the exposure.
    3. ``auth_config`` -- an explicit :class:`JWTConfig` (or a ``dict`` of its
       fields). Used as given.
    4. The environment, via :func:`build_server_auth_config`. Raises
       :class:`ServerAuthNotConfiguredError` when nothing is configured.

    Note:
        An ``auth_manager`` does NOT satisfy this gate and is deliberately not
        consulted here. ``auth_manager`` supplies a FastAPI ``Depends``, and a
        dependency does not run for routes inside a mounted sub-application --
        which is precisely the surface ``/workflows/{name}/execute`` lives on.
        Accepting it would close the gate on paper and leave the reachable
        route open.

    Args:
        require_auth: Whether this server must authenticate every request.
        auth_config: Explicit ``JWTConfig`` or field ``dict``.
        external_auth_reason: Non-empty when auth is provided externally.
        extra_exempt_paths: Additional paths exempt from authentication.
        server_label: Name used in messages.
        env: Environment mapping to read (defaults to ``os.environ``).

    Returns:
        The ``JWTConfig`` to install, or ``None`` when nothing should be
        installed on this server.

    Raises:
        ServerAuthNotConfiguredError: ``require_auth=True`` and no credential.
        InvalidServerAuthSecretError: Configured secret is under-length.
        ValueError: ``external_auth_reason`` was supplied but blank.
    """
    if external_auth_reason is not None:
        if not str(external_auth_reason).strip():
            raise ValueError(
                "external_auth_reason must be a non-empty string naming what "
                "authenticates requests instead of this server (e.g. "
                "'nexus installs nexus.auth.jwt.JWTMiddleware'). A blank "
                "reason disables the gate with nothing on the record."
            )
        logger.info(
            "server_auth.external",
            extra={
                "server": server_label,
                "reason": str(external_auth_reason).strip(),
            },
        )
        return None

    if not require_auth:
        # An explicit opt-out is a legitimate choice (local development,
        # a server behind an authenticating proxy) but it is never silent:
        # security.md § Secure-Default requires the OFF protection and its
        # exact wiring to be named.
        logger.warning(
            "server_auth.disabled",
            extra={
                "server": server_label,
                "exposure": (
                    "every route is served to anonymous callers, including "
                    "POST /workflows/{name}/execute which runs arbitrary "
                    "registered workflows"
                ),
                "wiring": (
                    f"remove require_auth=False and set {JWT_SECRET_ENV}, or "
                    "pass auth_config=JWTConfig(...)"
                ),
            },
        )
        return None

    if auth_config is not None:
        from kailash.trust.auth.jwt import JWTConfig

        if isinstance(auth_config, JWTConfig):
            return auth_config
        if isinstance(auth_config, dict):
            # An empty dict is NOT a config. Treating it as one would build a
            # JWTConfig with no secret and hand back a server that installs a
            # middleware which can never verify anything -- the silent-no-op
            # shape this whole module exists to prevent. Fall through to the
            # environment instead, which fails closed.
            if auth_config:
                return JWTConfig(**auth_config)
        else:
            raise TypeError(
                "auth_config must be a JWTConfig or a dict of its fields, "
                f"got {type(auth_config).__name__}."
            )

    return build_server_auth_config(
        extra_exempt_paths=extra_exempt_paths,
        env=env,
        server_label=server_label,
    )


def install_server_auth_middleware(app: Any, config: "JWTConfig") -> None:
    """Install :class:`~kailash.trust.auth.asgi.JWTAuthMiddleware` onto ``app``.

    Args:
        app: The FastAPI/Starlette application to protect.
        config: The resolved JWT configuration.

    Raises:
        RuntimeError: The application has already started, so Starlette has
            frozen its middleware stack and the auth layer would never run.

    Note:
        MUST be called BEFORE ``CORSMiddleware`` is added. Starlette's
        ``add_middleware`` prepends, so the LAST layer added is the OUTERMOST
        one; auth added after CORS ends up inside it and rejects cross-origin
        preflight ``OPTIONS`` with 401 before CORS can answer.
    """
    from kailash.trust.auth.asgi import JWTAuthMiddleware

    try:
        app.add_middleware(JWTAuthMiddleware, config=config)
    except RuntimeError as exc:
        # Swallowing this would hand back an app that reports auth as enabled
        # while serving every route unauthenticated -- the exact #2013 shape.
        raise RuntimeError(
            "Cannot install authentication: the application has already "
            "started, and Starlette freezes its middleware stack at startup, "
            "so the auth layer would never run. Construct the server with "
            f"require_auth=True before the first request. Underlying: {exc}"
        ) from exc

    logger.info(
        "server_auth.middleware_installed",
        extra={"exempt_paths": len(config.exempt_paths)},
    )
