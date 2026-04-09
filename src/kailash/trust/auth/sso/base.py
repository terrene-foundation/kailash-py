"""SSO Provider Protocol and Base Classes.

Defines the interface that all SSO providers must implement.

Evidence:
    - production SSO implementation references
    - production SSO implementation reference
    - production SSO implementation reference
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class SSOTokenResponse:
    """Response from SSO token exchange.

    Attributes:
        access_token: OAuth2 access token
        id_token: OIDC ID token (JWT with user claims)
        refresh_token: Refresh token (optional)
        token_type: Token type (usually "Bearer")
        expires_in: Token lifetime in seconds
        scope: Granted scopes (space-separated)
    """

    access_token: str
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: Optional[str] = None


@dataclass
class SSOUserInfo:
    """User information from SSO provider.

    Normalized representation of user data from any provider.

    Attributes:
        provider_user_id: User ID from the provider
        email: User email
        email_verified: Whether email is verified
        name: Full name
        given_name: First name
        family_name: Last name
        picture: Profile picture URL
        locale: User locale
        raw_data: Original response from provider
    """

    provider_user_id: str
    email: Optional[str] = None
    email_verified: bool = False
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    locale: Optional[str] = None
    raw_data: Dict[str, Any] = None

    def __post_init__(self):
        if self.raw_data is None:
            self.raw_data = {}


@runtime_checkable
class SSOProvider(Protocol):
    """Protocol for SSO providers.

    All SSO providers must implement this interface.

    Usage:
        >>> class CustomProvider:
        ...     name = "custom"
        ...
        ...     def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        ...         return f"https://custom.auth.com/authorize?state={state}"
        ...
        ...     async def exchange_code(self, code: str, redirect_uri: str) -> SSOTokenResponse:
        ...         ...
        ...
        ...     async def get_user_info(self, access_token: str) -> SSOUserInfo:
        ...         ...
        ...
        ...     def validate_id_token(self, id_token: str) -> dict:
        ...         ...
    """

    @property
    def name(self) -> str:
        """Provider name (used in routes: /auth/sso/{name}/)."""
        ...

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate authorization URL for OAuth2 flow.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL after authorization
            scope: OAuth2 scopes (optional, uses provider default)
            **kwargs: Provider-specific parameters

        Returns:
            Full authorization URL to redirect user to
        """
        ...

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            redirect_uri: Same redirect_uri used in authorization

        Returns:
            Token response with access_token and optionally id_token

        Raises:
            SSOAuthError: If code exchange fails
        """
        ...

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user information using access token.

        Args:
            access_token: OAuth2 access token

        Returns:
            Normalized user information

        Raises:
            SSOAuthError: If user info fetch fails
        """
        ...

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """Validate and decode ID token.

        Args:
            id_token: OIDC ID token (JWT)

        Returns:
            Decoded token claims

        Raises:
            SSOAuthError: If token is invalid
        """
        ...


class BaseSSOProvider:
    """Base class for SSO providers with common functionality.

    Provides:
        - HTTP client management
        - Common error handling
        - Token validation utilities
    """

    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str] = None,
        timeout: int = 30,
    ):
        """Initialize base provider.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret (optional for some providers)
            timeout: HTTP request timeout in seconds
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._http_client = None

    async def _get_http_client(self):
        """Get or create async HTTP client."""
        if self._http_client is None:
            import httpx

            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client

    async def _post_form(
        self,
        url: str,
        data: Dict[str, str],
    ) -> Dict[str, Any]:
        """Make POST request with form data.

        Args:
            url: Request URL
            data: Form data

        Returns:
            JSON response

        Raises:
            SSOAuthError: If request fails
        """
        client = await self._get_http_client()
        response = await client.post(url, data=data)

        if response.status_code != 200:
            # SECURITY: Log full details server-side, return sanitized error
            logger.warning(
                "SSO token exchange failed: status=%d, body=%s",
                response.status_code,
                response.text[:500],  # Truncate to prevent log flooding
            )
            raise SSOAuthError(
                f"Token exchange failed with status {response.status_code}"
            )

        return response.json()

    async def _get_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make GET request expecting JSON response.

        Args:
            url: Request URL
            headers: Optional headers

        Returns:
            JSON response

        Raises:
            SSOAuthError: If request fails
        """
        client = await self._get_http_client()
        response = await client.get(url, headers=headers or {})

        if response.status_code != 200:
            # SECURITY: Log full details server-side, return sanitized error
            logger.warning(
                "SSO user info fetch failed: status=%d, body=%s",
                response.status_code,
                response.text[:500],
            )
            raise SSOAuthError(
                f"User info fetch failed with status {response.status_code}"
            )

        return response.json()

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class SSOAuthError(Exception):
    """SSO authentication error."""

    pass
