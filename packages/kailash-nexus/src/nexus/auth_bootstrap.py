# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Wire ``Nexus(enable_auth=True)`` to a REAL HTTP authentication control.

Issue #2013. Before this module existed, ``enable_auth=True`` set three
booleans (``Nexus._enable_auth``, ``Nexus._auth_enabled``,
``HTTPTransport._enable_auth``) and installed nothing. The two code paths that
looked like they installed something were both structural ``hasattr`` guards
over names that have ZERO definitions anywhere in the repo or its dependencies:

* ``nexus/plugins.py``  -- ``if hasattr(gateway, "set_auth_manager")``
* ``nexus/core.py``     -- ``if gw and hasattr(gw, "enable_auth")``

The gateway is ``kailash.servers.EnterpriseWorkflowServer``, which exposes no
authentication surface at all (``grep -rnE 'Depends\\(|HTTPBearer|APIKeyHeader'
src/kailash/servers/`` returns zero matches). Both guards were therefore
permanently False, so ``enable_auth=True`` was a documented security control
that left every route unauthenticated -- the silent-fallback shape
``rules/zero-tolerance.md`` Rule 3d enumerates.

This module installs ``nexus.auth.jwt.JWTMiddleware`` -- a real Starlette
middleware that rejects unauthenticated requests with 401 -- onto the gateway's
FastAPI app, and FAILS LOUD when it cannot. Per ``rules/security.md``
§ Secure-Default, an auth switch that silently succeeds without installing
anything is the worst outcome; refusing to construct is the correct one, and it
matches the precedent already set for the same defect class in
``APIGateway(enable_auth=True)`` (issue #636).

Credentials come from the environment (``rules/env-models.md``: ``.env`` is the
single source of truth):

* ``NEXUS_JWT_SECRET``      -- HS256 signing secret, minimum 32 bytes.
* ``NEXUS_JWT_PUBLIC_KEY``  -- PEM public key for RS*/ES* verification.
* ``NEXUS_JWT_ALGORITHM``   -- defaults to ``HS256``.
* ``NEXUS_API_KEY_<NAME>``  -- one or more API keys; enables ``X-API-Key`` auth.
* ``NEXUS_AUTH_EXEMPT_PATHS`` -- comma-separated extra exempt paths.

At least one credential source MUST be present, otherwise
:class:`AuthNotConfiguredError` is raised naming every accepted variable.
"""

from __future__ import annotations

import logging
import os
import secrets
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover -- typing only
    from kailash.trust.auth.jwt import JWTConfig

logger = logging.getLogger(__name__)

__all__ = [
    "AuthNotConfiguredError",
    "InvalidAuthSecretError",
    "API_KEY_ENV_PREFIX",
    "EXEMPT_PATHS_ENV",
    "JWT_ALGORITHM_ENV",
    "JWT_PUBLIC_KEY_ENV",
    "JWT_SECRET_ENV",
    "MIN_SECRET_BYTES",
    "build_auth_config",
    "collect_api_keys",
    "install_auth_middleware",
]

JWT_SECRET_ENV = "NEXUS_JWT_SECRET"
JWT_PUBLIC_KEY_ENV = "NEXUS_JWT_PUBLIC_KEY"
JWT_ALGORITHM_ENV = "NEXUS_JWT_ALGORITHM"
API_KEY_ENV_PREFIX = "NEXUS_API_KEY_"
EXEMPT_PATHS_ENV = "NEXUS_AUTH_EXEMPT_PATHS"

#: RFC 7518 §3.2 -- an HS256 key MUST be at least as long as the hash output.
MIN_SECRET_BYTES = 32

#: Liveness/readiness probes must answer without credentials, or every
#: orchestrator marks an authenticated Nexus unhealthy and restarts it.
#: Nothing else is exempt by default: ``/docs``, ``/metrics``, ``/`` and every
#: workflow route describe or expose the protected surface.
DEFAULT_EXEMPT_PATHS: tuple[str, ...] = (
    "/health",
    "/health/*",
    "/enterprise/health",
)


class AuthNotConfiguredError(RuntimeError):
    """``enable_auth=True`` with no credential source in the environment.

    Subclasses :class:`RuntimeError` so existing ``except RuntimeError``
    handlers keep working, mirroring the ``APIGateway`` fix for issue #636.
    """


class InvalidAuthSecretError(ValueError):
    """A configured signing secret is present but too weak to use.

    Subclasses :class:`ValueError` to match the ``APIGateway`` precedent for
    the same defect class (issue #636), while remaining distinguishable from
    unrelated ``ValueError``s raised during gateway construction -- ``Nexus``
    re-raises this type unwrapped so the operator sees the actionable message.
    """


def collect_api_keys(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return ``{NEXUS_API_KEY_<NAME>: value}`` for every non-empty API key.

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

    ``secrets.compare_digest`` is mandatory here: a plain ``==`` short-circuits
    on the first differing byte and leaks the key prefix under a remote-timing
    oracle (see ``JWTConfig.api_key_validator``'s own SECURITY note). The loop
    below compares against EVERY configured key rather than returning early, so
    the number of comparisons does not depend on which key matched.
    """
    expected = list(api_keys.values())

    def _validate(api_key: str) -> bool:
        matched = False
        for candidate in expected:
            if secrets.compare_digest(api_key, candidate):
                matched = True
        return matched

    return _validate


def _exempt_paths(extra: Optional[List[str]] = None) -> List[str]:
    paths = list(DEFAULT_EXEMPT_PATHS)
    raw = os.environ.get(EXEMPT_PATHS_ENV, "")
    paths.extend(p.strip() for p in raw.split(",") if p.strip())
    if extra:
        paths.extend(extra)
    # dict.fromkeys preserves order while removing duplicates.
    return list(dict.fromkeys(paths))


def build_auth_config(
    *,
    extra_exempt_paths: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> "JWTConfig":
    """Build a :class:`JWTConfig` from the environment, or fail loud.

    Args:
        extra_exempt_paths: Paths appended to the built-in exempt list.
        env: Environment mapping to read (defaults to ``os.environ``).

    Returns:
        A ``JWTConfig`` with at least one credential source wired.

    Raises:
        AuthNotConfiguredError: No credential source is present. Auth cannot be
            installed, and proceeding without it would leave the API open while
            reporting that authentication is enabled.
        InvalidAuthSecretError: ``NEXUS_JWT_SECRET`` is present but shorter
            than :data:`MIN_SECRET_BYTES`.
        ImportError: PyJWT is not installed (the ``kailash[trust]`` extra).
    """
    source = os.environ if env is None else env

    # Imported function-locally: kailash.trust.auth.jwt raises ImportError at
    # module scope when PyJWT is absent, and that must surface at
    # enable_auth-time with actionable wiring rather than at nexus import time.
    from kailash.trust.auth.jwt import JWTConfig

    secret = source.get(JWT_SECRET_ENV) or None
    public_key = source.get(JWT_PUBLIC_KEY_ENV) or None
    algorithm = source.get(JWT_ALGORITHM_ENV) or "HS256"
    api_keys = collect_api_keys(source)

    if not (secret or public_key or api_keys):
        raise AuthNotConfiguredError(
            "Nexus authentication is enabled but no credential source is "
            "configured, so no authentication could be installed. Refusing to "
            "start with an unauthenticated API while reporting auth as "
            "enabled (issue #2013).\n"
            f"Set one of:\n"
            f"  {JWT_SECRET_ENV}=<at least {MIN_SECRET_BYTES} bytes>   "
            "(HS256 bearer tokens)\n"
            f"  {JWT_PUBLIC_KEY_ENV}=<PEM public key>          "
            f"(with {JWT_ALGORITHM_ENV}=RS256/ES256)\n"
            f"  {API_KEY_ENV_PREFIX}<NAME>=<key>                 "
            "(X-API-Key header)\n"
            "Or construct with Nexus(enable_auth=False) to run without "
            "authentication."
        )

    if secret is not None and len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise InvalidAuthSecretError(
            f"{JWT_SECRET_ENV} must be at least {MIN_SECRET_BYTES} bytes "
            f"(got {len(secret.encode('utf-8'))}). A short HS256 key is "
            "brute-forceable; see RFC 7518 §3.2."
        )

    if secret is None and public_key is None:
        # API-key-only deployment. JWTConfig.__post_init__ rejects a symmetric
        # algorithm with no secret, so the bearer arm needs SOME key -- and the
        # fail-CLOSED choice is a fresh random one that is never written down
        # or returned. No party can mint a token against it, so every Bearer
        # request is rejected while the X-API-Key arm works. Falling back to a
        # fixed or empty secret here would forge-enable the whole JWT path.
        secret = secrets.token_urlsafe(48)
        logger.info(
            "No JWT credential configured; bearer-token auth is disabled "
            "(unforgeable ephemeral key) and X-API-Key is the only accepted "
            "credential."
        )

    config = JWTConfig(
        secret=secret,
        public_key=public_key,
        algorithm=algorithm,
        exempt_paths=_exempt_paths(extra_exempt_paths),
        api_key_enabled=bool(api_keys),
        api_key_validator=_make_api_key_validator(api_keys) if api_keys else None,
    )

    logger.info(
        "Nexus auth configured: jwt_secret=%s public_key=%s algorithm=%s "
        "api_keys=%d exempt_paths=%d",
        bool(secret),
        bool(public_key),
        algorithm,
        len(api_keys),
        len(config.exempt_paths),
    )
    return config


def _jwt_middleware_class():
    """Import ``JWTMiddleware`` without emitting the package deprecation notice.

    ``nexus.auth.__init__`` warns importers to migrate to ``kailash.trust.auth``
    (SPEC-06). That guidance is for callers; the Starlette middleware itself has
    NOT moved -- ``kailash.trust.auth.jwt`` keeps only the framework-agnostic
    ``JWTValidator`` -- so this internal import is the canonical one and must
    not tell users to migrate away from it.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from nexus.auth.jwt import JWTMiddleware

    return JWTMiddleware


def install_auth_middleware(
    nexus_instance: Any,
    *,
    extra_exempt_paths: Optional[List[str]] = None,
) -> "JWTConfig":
    """Install JWT/API-key authentication onto the Nexus HTTP app.

    Idempotent: a second call returns the already-installed config without
    adding a duplicate middleware layer.

    Args:
        nexus_instance: The ``Nexus`` instance whose HTTP transport to protect.
        extra_exempt_paths: Paths appended to the built-in exempt list.

    Returns:
        The installed ``JWTConfig``.

    Raises:
        AuthNotConfiguredError: No credential source configured, or the HTTP
            transport has no gateway to protect.
        RuntimeError: The application has already started, so Starlette can no
            longer accept new middleware -- enable auth before the first
            request.
        InvalidAuthSecretError: The configured secret is under-length.
    """
    installed = getattr(nexus_instance, "_auth_config", None)
    if installed is not None:
        return installed

    transport = getattr(nexus_instance, "_http_transport", None)
    if transport is None or transport.gateway is None:
        raise AuthNotConfiguredError(
            "Cannot install authentication: the Nexus HTTP transport has no "
            "gateway yet. Authentication is installed during Nexus.__init__ "
            "once the gateway exists; calling this earlier leaves the API "
            "unauthenticated."
        )

    config = build_auth_config(extra_exempt_paths=extra_exempt_paths)
    try:
        transport.add_middleware(_jwt_middleware_class(), config=config)
    except RuntimeError as e:
        # Starlette freezes user_middleware the first time the app is built,
        # and raises "Cannot add middleware after an application has started".
        # Swallowing that would hand back an app that reports auth as enabled
        # while serving every route unauthenticated -- the exact #2013 shape --
        # so it is re-raised with the actionable wiring instead.
        raise RuntimeError(
            "Cannot install authentication: the application has already "
            "started, and Starlette freezes its middleware stack at startup, "
            "so the auth layer would never run. Enable auth BEFORE the first "
            "request by constructing Nexus(enable_auth=True), or by calling "
            f"app.enable_auth() before app.start(). Underlying error: {e}"
        ) from e

    nexus_instance._auth_config = config
    nexus_instance._auth_enabled = True
    logger.info(
        "Authentication middleware installed on the Nexus HTTP app "
        "(unauthenticated requests now receive 401)"
    )
    return config
