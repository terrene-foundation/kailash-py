"""SSO Provider exports and convenience functions.

Usage:
    >>> from nexus.auth.sso import AzureADProvider, GoogleProvider, AppleProvider
    >>>
    >>> # Configure providers
    >>> azure = AzureADProvider(...)
    >>> google = GoogleProvider(...)
    >>>
    >>> # Use with NexusAuthPlugin
    >>> auth = NexusAuthPlugin(sso_providers=[azure, google])
    >>>
    >>> # For production multi-process deployments, configure a custom state store:
    >>> from nexus.auth.sso import configure_state_store
    >>> configure_state_store(my_redis_state_store)
"""

import logging
import secrets
import time
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from nexus.auth.sso.apple import AppleProvider
from nexus.auth.sso.azure import AzureADProvider
from nexus.auth.sso.base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOProvider,
    SSOTokenResponse,
    SSOUserInfo,
)
from nexus.auth.sso.github import GitHubProvider
from nexus.auth.sso.google import GoogleProvider

__all__ = [
    # Protocol and base
    "SSOProvider",
    "BaseSSOProvider",
    "SSOTokenResponse",
    "SSOUserInfo",
    "SSOAuthError",
    # Providers
    "AzureADProvider",
    "GoogleProvider",
    "AppleProvider",
    "GitHubProvider",
    # State store
    "SSOStateStore",
    "InMemorySSOStateStore",
    "configure_state_store",
    # Helper functions
    "initiate_sso_login",
    "handle_sso_callback",
    "exchange_sso_code",
    "InvalidStateError",
]

logger = logging.getLogger(__name__)

_SSO_STATE_TTL_SECONDS = 600  # 10 minutes


class InvalidStateError(Exception):
    """Raised when SSO state is invalid or expired."""

    pass


# --- Pluggable State Store ---


@runtime_checkable
class SSOStateStore(Protocol):
    """Protocol for SSO CSRF state storage.

    Implementations must provide store, validate, and cleanup methods.
    The default InMemorySSOStateStore is suitable for single-process
    development only. For production multi-process or multi-server
    deployments, use a Redis-backed implementation.

    The store persists — alongside the CSRF state token — the per-flow PKCE
    ``code_verifier`` (RFC 7636) and OIDC ``nonce`` minted at authorization
    time, so :func:`handle_sso_callback` can replay the verifier to the token
    endpoint and enforce the nonce against the returned id_token.
    ``validate_and_consume`` returns the stored data dict on a valid,
    single-use consume and ``None`` when the state is unknown or expired.

    Example Redis implementation:
        >>> import json
        >>> class RedisSSOStateStore:
        ...     def __init__(self, redis_client, ttl=600):
        ...         self._redis = redis_client
        ...         self._ttl = ttl
        ...
        ...     def store(self, state, *, code_verifier=None, nonce=None):
        ...         payload = json.dumps(
        ...             {"code_verifier": code_verifier, "nonce": nonce}
        ...         )
        ...         self._redis.setex(f"sso:state:{state}", self._ttl, payload)
        ...
        ...     def validate_and_consume(self, state):
        ...         key = f"sso:state:{state}"
        ...         pipe = self._redis.pipeline()
        ...         pipe.get(key)
        ...         pipe.delete(key)
        ...         result = pipe.execute()
        ...         if result[0] is None:
        ...             return None
        ...         return json.loads(result[0])
        ...
        ...     def cleanup(self) -> None:
        ...         pass  # Redis TTL handles expiration
    """

    def store(
        self,
        state: str,
        *,
        code_verifier: Optional[str] = None,
        nonce: Optional[str] = None,
    ) -> None:
        """Store a new CSRF state token with its PKCE verifier + OIDC nonce."""
        ...

    def validate_and_consume(self, state: str) -> Optional[Dict[str, Any]]:
        """Validate state token and remove it (single use).

        Returns:
            The stored ``{"code_verifier": ..., "nonce": ...}`` dict if the
            state was valid and not expired, ``None`` otherwise. The dict is
            truthy on success so ``if not store.validate_and_consume(state)``
            remains a correct validity gate.
        """
        ...

    def cleanup(self) -> None:
        """Remove expired state entries."""
        ...


class InMemorySSOStateStore:
    """In-memory SSO state store for development.

    WARNING: Not suitable for production multi-process deployments.
    State is not shared between workers/servers and is lost on restart.
    Use a Redis-backed store for production.
    """

    def __init__(self, ttl_seconds: int = 600):
        # state -> {"timestamp": float, "code_verifier": str|None, "nonce": str|None}
        self._store: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds

    def store(
        self,
        state: str,
        *,
        code_verifier: Optional[str] = None,
        nonce: Optional[str] = None,
    ) -> None:
        """Store a new state token with its PKCE verifier + OIDC nonce."""
        self.cleanup()
        self._store[state] = {
            "timestamp": time.time(),
            "code_verifier": code_verifier,
            "nonce": nonce,
        }

    def validate_and_consume(self, state: str) -> Optional[Dict[str, Any]]:
        """Validate and atomically consume state token.

        Returns the stored ``{"code_verifier", "nonce"}`` dict on success,
        ``None`` when the state is unknown or expired.
        """
        entry = self._store.pop(state, None)
        if entry is None:
            return None
        if time.time() - entry["timestamp"] > self._ttl:
            return None
        return {
            "code_verifier": entry.get("code_verifier"),
            "nonce": entry.get("nonce"),
        }

    def cleanup(self) -> None:
        """Remove expired state entries."""
        now = time.time()
        expired = [
            k for k, v in self._store.items() if now - v["timestamp"] > self._ttl
        ]
        for k in expired:
            del self._store[k]


# Default state store (single-process only)
_state_store: SSOStateStore = InMemorySSOStateStore()


def configure_state_store(store: SSOStateStore) -> None:
    """Configure the SSO state store for production deployments.

    Call this during application startup to replace the default
    in-memory store with a distributed implementation (e.g., Redis).

    Args:
        store: SSOStateStore implementation

    Example:
        >>> from nexus.auth.sso import configure_state_store
        >>> configure_state_store(RedisSSOStateStore(redis_client))
    """
    global _state_store
    if not isinstance(store, SSOStateStore):
        raise TypeError(
            f"State store must implement SSOStateStore protocol, "
            f"got {type(store).__name__}"
        )
    _state_store = store
    logger.info("SSO state store configured: %s", type(store).__name__)


def _get_state_store() -> SSOStateStore:
    """Get the current state store instance."""
    return _state_store


# --- SSO Flow Functions ---


async def initiate_sso_login(
    provider: SSOProvider,
    callback_base_url: str,
    **kwargs,
):
    """Initiate SSO login flow.

    Args:
        provider: SSO provider instance
        callback_base_url: Base URL for callback (e.g., "https://myapp.com")
        **kwargs: Additional parameters for authorization URL

    Returns:
        Redirect response to provider's authorization page
    """
    from fastapi.responses import RedirectResponse

    state = secrets.token_urlsafe(32)

    redirect_uri = f"{callback_base_url}/auth/sso/{provider.name}/callback"

    # PKCE (RFC 7636) — a per-flow verifier/challenge pair bound to this state.
    code_verifier, code_challenge = provider.generate_pkce_pair()

    # OIDC nonce (id_token replay/injection defense) — minted ONLY for providers
    # that issue an id_token (GitHub OAuth2 has none, so no nonce).
    nonce = (
        secrets.token_urlsafe(32)
        if getattr(provider, "supports_id_token", False)
        else None
    )
    if nonce is not None:
        kwargs["nonce"] = nonce

    auth_url = provider.get_authorization_url(
        state=state,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        **kwargs,
    )

    store = _get_state_store()
    store.store(state, code_verifier=code_verifier, nonce=nonce)

    return RedirectResponse(url=auth_url)


async def handle_sso_callback(
    provider: SSOProvider,
    code: str,
    state: str,
    auth_plugin: Any,  # NexusAuthPlugin
    callback_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle SSO callback and issue JWT.

    Args:
        provider: SSO provider instance
        code: Authorization code from callback
        state: CSRF state parameter
        auth_plugin: NexusAuthPlugin instance
        callback_base_url: Base URL for callback

    Returns:
        JWT token response

    Raises:
        InvalidStateError: If CSRF state doesn't match or is expired
        SSOAuthError: If SSO authentication fails
    """
    store = _get_state_store()
    state_result = store.validate_and_consume(state)
    if not state_result:
        raise InvalidStateError("Invalid or expired SSO state - possible CSRF attack")

    # A dict-returning store carries the per-flow PKCE verifier + nonce; a legacy
    # bool-returning custom store carries neither (empty dict), so PKCE/nonce are
    # simply absent — never a silent downgrade of a flow that DID mint them.
    state_data = state_result if isinstance(state_result, dict) else {}
    code_verifier = state_data.get("code_verifier")
    nonce = state_data.get("nonce")

    redirect_uri = f"{callback_base_url or ''}/auth/sso/{provider.name}/callback"

    tokens = await provider.exchange_code(
        code, redirect_uri, code_verifier=code_verifier
    )

    if tokens.id_token:
        # nonce enforcement runs inside validate_id_token against the
        # JWKS-verified claims (fail-closed on mismatch).
        claims = provider.validate_id_token(tokens.id_token, nonce=nonce)
        user_id = claims.get("sub")
        email = claims.get("email")
        name = claims.get("name")
    else:
        user_info = await provider.get_user_info(tokens.access_token)
        user_id = user_info.provider_user_id
        email = user_info.email
        name = user_info.name

    jwt_middleware = auth_plugin._jwt_middleware

    access_token = jwt_middleware.create_access_token(
        user_id=f"{provider.name}:{user_id}",
        email=email,
        roles=[],
    )

    refresh_token = jwt_middleware.create_refresh_token(
        user_id=f"{provider.name}:{user_id}",
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "provider": provider.name,
        },
    }


async def exchange_sso_code(
    provider: SSOProvider,
    code: str,
    state: str,
    auth_plugin: Any,
    redirect_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange SSO code for tokens (SPA flow).

    For SPAs that handle the OAuth flow client-side and need to
    exchange the code for tokens via API.

    SECURITY: The state parameter is required for CSRF protection.
    SPAs must store the state from initiate_sso_login() and pass it
    back here for validation.

    Args:
        provider: SSO provider instance
        code: Authorization code
        state: CSRF state parameter (from initiate_sso_login)
        auth_plugin: NexusAuthPlugin instance
        redirect_uri: Redirect URI used in authorization

    Returns:
        JWT token response

    Raises:
        InvalidStateError: If state is missing, invalid, or expired
        SSOAuthError: If SSO authentication fails
    """
    if not state:
        raise InvalidStateError(
            "CSRF state parameter is required for SSO code exchange. "
            "Pass the state value returned by initiate_sso_login()."
        )

    return await handle_sso_callback(
        provider=provider,
        code=code,
        state=state,
        auth_plugin=auth_plugin,
        callback_base_url=redirect_uri,
    )
