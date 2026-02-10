# SSO Providers Specification

## Overview

This specification defines the Single Sign-On (SSO) provider system for NexusAuthPlugin. It supports OAuth2/OIDC flows for Azure AD, Google, Apple Sign-In, and GitHub.

**Evidence from Production Projects:**

- **example-app**: `utils/azure_jwt.py` (301 lines), `utils/apple_jwt.py` (276 lines), `endpoints/oauth.py`
- **example-project**: `auth_platform.py`, `workflows/AUTH_WORKFLOWS_SUMMARY.md`
- **enterprise-app**: `config/sso.py`, `api/sso.py`

---

## File Structure

```
apps/kailash-nexus/src/nexus/auth/sso/
    __init__.py          # Exports, convenience functions
    base.py              # SSOProvider protocol
    azure.py             # AzureADProvider
    google.py            # GoogleProvider
    apple.py             # AppleProvider
    github.py            # GitHubProvider
```

---

## SSO Provider Protocol

### Location

`/apps/kailash-nexus/src/nexus/auth/sso/base.py`

### Implementation

```python
"""SSO Provider Protocol and Base Classes.

Defines the interface that all SSO providers must implement.

Evidence:
    - example-app: utils/azure_jwt.py, utils/apple_jwt.py
    - example-project: auth_platform.py
    - enterprise-app: config/sso.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
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
        ...         return f"https://custom.auth.com/authorize?state={state}&redirect_uri={redirect_uri}"
        ...
        ...     async def exchange_code(self, code: str, redirect_uri: str) -> SSOTokenResponse:
        ...         # Exchange authorization code for tokens
        ...         ...
        ...
        ...     async def get_user_info(self, access_token: str) -> SSOUserInfo:
        ...         # Fetch user info using access token
        ...         ...
        ...
        ...     def validate_id_token(self, id_token: str) -> dict:
        ...         # Validate and decode ID token
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
            raise SSOAuthError(
                f"Token exchange failed: {response.status_code} - {response.text}"
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
            raise SSOAuthError(
                f"User info fetch failed: {response.status_code} - {response.text}"
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
```

---

## Azure AD Provider

### Location

`/apps/kailash-nexus/src/nexus/auth/sso/azure.py`

### Implementation

```python
"""Azure AD (Microsoft Entra ID) SSO Provider.

Provides OAuth2/OIDC authentication with Microsoft Azure AD.

Supports:
    - Single-tenant and multi-tenant apps
    - JWKS-based token validation
    - User info from Microsoft Graph API

Evidence:
    - example-app: utils/azure_jwt.py (301 lines)
        - JWKS URL construction
        - Tenant ID validation
        - Audience validation
        - Token expiry handling
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient

from .base import BaseSSOProvider, SSOAuthError, SSOTokenResponse, SSOUserInfo

logger = logging.getLogger(__name__)


class AzureADProvider(BaseSSOProvider):
    """Azure AD (Microsoft Entra ID) SSO provider.

    Usage:
        >>> from nexus.auth.sso import AzureADProvider
        >>>
        >>> azure = AzureADProvider(
        ...     tenant_id="your-tenant-id",
        ...     client_id="your-client-id",
        ...     client_secret="your-client-secret",
        ... )

    Endpoints (single tenant):
        - Authorization: https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize
        - Token: https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
        - JWKS: https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
        - User Info: https://graph.microsoft.com/v1.0/me

    Endpoints (multi-tenant):
        - Use "common" or "organizations" instead of tenant_id
        - Validate tenant_id claim in token

    Evidence:
        From example-app/utils/azure_jwt.py:
        - Lines 45-67: JWKS URL construction
        - Lines 89-130: Token verification with audience/issuer
        - Lines 180-220: Error handling for expired/invalid tokens
    """

    name = "azure"

    # Azure AD endpoints
    AUTHORITY_BASE = "https://login.microsoftonline.com"
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        # Optional settings
        scopes: Optional[List[str]] = None,
        allowed_tenants: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize Azure AD provider.

        Args:
            tenant_id: Azure AD tenant ID (or "common" for multi-tenant)
            client_id: Application (client) ID
            client_secret: Client secret
            scopes: OAuth2 scopes (default: openid, profile, email)
            allowed_tenants: For multi-tenant apps, list of allowed tenant IDs
            timeout: HTTP request timeout

        Evidence:
            From example-app/utils/azure_jwt.py lines 25-45
        """
        super().__init__(client_id, client_secret, timeout)
        self.tenant_id = tenant_id
        self.scopes = scopes or ["openid", "profile", "email", "User.Read"]
        self.allowed_tenants = allowed_tenants
        self.is_multi_tenant = tenant_id in ("common", "organizations", "consumers")

        # Initialize JWKS client for token validation
        self._jwks_client = PyJWKClient(
            f"{self.AUTHORITY_BASE}/{tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
            lifespan=3600,  # Cache keys for 1 hour
        )

        logger.info(
            f"AzureADProvider initialized: tenant={tenant_id}, "
            f"multi_tenant={self.is_multi_tenant}"
        )

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        prompt: str = "select_account",
        **kwargs,
    ) -> str:
        """Generate Azure AD authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes (space-separated)
            prompt: Login prompt behavior (none, login, consent, select_account)
            **kwargs: Additional parameters (login_hint, domain_hint, etc.)

        Returns:
            Authorization URL

        Evidence:
            From example-app/endpoints/oauth.py authorization flow
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "response_mode": "query",
            "prompt": prompt,
        }
        params.update(kwargs)

        base_url = f"{self.AUTHORITY_BASE}/{self.tenant_id}/oauth2/v2.0/authorize"
        return f"{base_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            redirect_uri: Same redirect URI used in authorization

        Returns:
            Token response with access_token and id_token

        Raises:
            SSOAuthError: If exchange fails

        Evidence:
            From example-app/utils/azure_jwt.py token exchange
        """
        token_url = f"{self.AUTHORITY_BASE}/{self.tenant_id}/oauth2/v2.0/token"

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        response = await self._post_form(token_url, data)

        return SSOTokenResponse(
            access_token=response["access_token"],
            id_token=response.get("id_token"),
            refresh_token=response.get("refresh_token"),
            token_type=response.get("token_type", "Bearer"),
            expires_in=response.get("expires_in", 3600),
            scope=response.get("scope"),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user info from Microsoft Graph API.

        Args:
            access_token: OAuth2 access token

        Returns:
            Normalized user information

        Evidence:
            From example-app Graph API integration
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        data = await self._get_json(f"{self.GRAPH_API_BASE}/me", headers=headers)

        return SSOUserInfo(
            provider_user_id=data.get("id"),
            email=data.get("mail") or data.get("userPrincipalName"),
            email_verified=True,  # Azure AD verifies emails
            name=data.get("displayName"),
            given_name=data.get("givenName"),
            family_name=data.get("surname"),
            picture=None,  # Graph API requires separate call for photo
            locale=data.get("preferredLanguage"),
            raw_data=data,
        )

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """Validate and decode Azure AD ID token.

        Validates:
            - Signature using JWKS
            - Expiration (exp claim)
            - Audience (aud claim = client_id)
            - Issuer (iss claim = Azure AD)
            - Tenant ID (tid claim, for multi-tenant)

        Args:
            id_token: JWT ID token

        Returns:
            Decoded token claims

        Raises:
            SSOAuthError: If validation fails

        Evidence:
            From example-app/utils/azure_jwt.py lines 89-180
        """
        try:
            # Get signing key from JWKS
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)

            # Determine expected issuer
            if self.is_multi_tenant:
                # For multi-tenant, decode first to get tid
                unverified = jwt.decode(
                    id_token,
                    options={"verify_signature": False}
                )
                tid = unverified.get("tid")
                if self.allowed_tenants and tid not in self.allowed_tenants:
                    raise SSOAuthError(f"Tenant {tid} not in allowed list")
                issuer = f"{self.AUTHORITY_BASE}/{tid}/v2.0"
            else:
                issuer = f"{self.AUTHORITY_BASE}/{self.tenant_id}/v2.0"

            # Validate and decode
            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=issuer,
            )

            return payload

        except jwt.ExpiredSignatureError:
            raise SSOAuthError("ID token has expired")
        except jwt.InvalidAudienceError:
            raise SSOAuthError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise SSOAuthError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise SSOAuthError(f"Invalid ID token: {e}")

    def get_logout_url(self, post_logout_redirect_uri: Optional[str] = None) -> str:
        """Get Azure AD logout URL.

        Args:
            post_logout_redirect_uri: URL to redirect after logout

        Returns:
            Logout URL
        """
        url = f"{self.AUTHORITY_BASE}/{self.tenant_id}/oauth2/v2.0/logout"
        if post_logout_redirect_uri:
            url += f"?post_logout_redirect_uri={post_logout_redirect_uri}"
        return url
```

---

## Google Provider

### Location

`/apps/kailash-nexus/src/nexus/auth/sso/google.py`

### Implementation

```python
"""Google OAuth2/OIDC SSO Provider.

Provides OAuth2/OIDC authentication with Google.

Evidence:
    - example-project: auth_platform.py Google OAuth flow
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient

from .base import BaseSSOProvider, SSOAuthError, SSOTokenResponse, SSOUserInfo

logger = logging.getLogger(__name__)


class GoogleProvider(BaseSSOProvider):
    """Google OAuth2/OIDC provider.

    Usage:
        >>> from nexus.auth.sso import GoogleProvider
        >>>
        >>> google = GoogleProvider(
        ...     client_id="your-client-id.apps.googleusercontent.com",
        ...     client_secret="your-client-secret",
        ... )

    Endpoints:
        - Authorization: https://accounts.google.com/o/oauth2/v2/auth
        - Token: https://oauth2.googleapis.com/token
        - JWKS: https://www.googleapis.com/oauth2/v3/certs
        - User Info: https://www.googleapis.com/oauth2/v3/userinfo
    """

    name = "google"

    # Google endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
    JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize Google provider.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            scopes: OAuth2 scopes (default: openid, profile, email)
            timeout: HTTP request timeout
        """
        super().__init__(client_id, client_secret, timeout)
        self.scopes = scopes or ["openid", "profile", "email"]

        # Initialize JWKS client
        self._jwks_client = PyJWKClient(
            self.JWKS_URL,
            cache_keys=True,
            lifespan=3600,
        )

        logger.info("GoogleProvider initialized")

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        access_type: str = "offline",
        prompt: str = "consent",
        **kwargs,
    ) -> str:
        """Generate Google authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes
            access_type: "online" or "offline" (for refresh token)
            prompt: "none", "consent", "select_account"
            **kwargs: Additional parameters (login_hint, hd for G Suite)

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "access_type": access_type,
            "prompt": prompt,
        }
        params.update(kwargs)

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code
            redirect_uri: Callback URL

        Returns:
            Token response

        Raises:
            SSOAuthError: If exchange fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        response = await self._post_form(self.TOKEN_URL, data)

        return SSOTokenResponse(
            access_token=response["access_token"],
            id_token=response.get("id_token"),
            refresh_token=response.get("refresh_token"),
            token_type=response.get("token_type", "Bearer"),
            expires_in=response.get("expires_in", 3600),
            scope=response.get("scope"),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user info from Google.

        Args:
            access_token: OAuth2 access token

        Returns:
            Normalized user information
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        data = await self._get_json(self.USERINFO_URL, headers=headers)

        return SSOUserInfo(
            provider_user_id=data.get("sub"),
            email=data.get("email"),
            email_verified=data.get("email_verified", False),
            name=data.get("name"),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
            picture=data.get("picture"),
            locale=data.get("locale"),
            raw_data=data,
        )

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """Validate and decode Google ID token.

        Args:
            id_token: JWT ID token

        Returns:
            Decoded token claims

        Raises:
            SSOAuthError: If validation fails
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
            )

            return payload

        except jwt.ExpiredSignatureError:
            raise SSOAuthError("ID token has expired")
        except jwt.InvalidAudienceError:
            raise SSOAuthError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise SSOAuthError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise SSOAuthError(f"Invalid ID token: {e}")
```

---

## Apple Provider

### Location

`/apps/kailash-nexus/src/nexus/auth/sso/apple.py`

### Implementation

```python
"""Apple Sign-In SSO Provider.

Provides OAuth2/OIDC authentication with Apple.

Apple Sign-In has unique characteristics:
    - Uses ES256 (ECDSA) for JWT signing
    - Client secret is a JWT signed with private key
    - Name is only returned on FIRST authorization
    - Email relay service for privacy

Evidence:
    - example-app: utils/apple_jwt.py (276 lines)
        - ES256 JWT verification
        - Client secret generation
        - Name relay handling
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient

from .base import BaseSSOProvider, SSOAuthError, SSOTokenResponse, SSOUserInfo

logger = logging.getLogger(__name__)


class AppleProvider(BaseSSOProvider):
    """Apple Sign-In provider.

    Usage:
        >>> from nexus.auth.sso import AppleProvider
        >>>
        >>> apple = AppleProvider(
        ...     team_id="YOUR_TEAM_ID",
        ...     client_id="com.yourapp.service",
        ...     key_id="YOUR_KEY_ID",
        ...     private_key_path="/path/to/AuthKey.p8",
        ... )

    Endpoints:
        - Authorization: https://appleid.apple.com/auth/authorize
        - Token: https://appleid.apple.com/auth/token
        - JWKS: https://appleid.apple.com/auth/keys

    Important Notes:
        - Apple only sends user's name on FIRST authorization
        - Store the name when received, it won't be sent again
        - Email may be a relay address (@privaterelay.appleid.com)

    Evidence:
        From example-app/utils/apple_jwt.py:
        - Lines 30-60: Client secret JWT generation
        - Lines 95-145: ES256 token verification
        - Lines 180-220: Name handling on first auth
    """

    name = "apple"

    # Apple endpoints
    AUTHORIZATION_URL = "https://appleid.apple.com/auth/authorize"
    TOKEN_URL = "https://appleid.apple.com/auth/token"
    JWKS_URL = "https://appleid.apple.com/auth/keys"

    def __init__(
        self,
        team_id: str,
        client_id: str,
        key_id: str,
        private_key: Optional[str] = None,
        private_key_path: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize Apple provider.

        Args:
            team_id: Apple Developer Team ID
            client_id: Service ID (e.g., "com.yourapp.service")
            key_id: Key ID from Apple Developer console
            private_key: Private key content (PEM format)
            private_key_path: Path to private key file (.p8)
            scopes: OAuth2 scopes (default: name, email)
            timeout: HTTP request timeout

        Raises:
            ValueError: If neither private_key nor private_key_path provided

        Evidence:
            From example-app/utils/apple_jwt.py lines 25-45
        """
        # Apple doesn't use client_secret in traditional sense
        super().__init__(client_id, None, timeout)

        self.team_id = team_id
        self.key_id = key_id
        self.scopes = scopes or ["name", "email"]

        # Load private key
        if private_key:
            self._private_key = private_key
        elif private_key_path:
            with open(private_key_path, "r") as f:
                self._private_key = f.read()
        else:
            raise ValueError("Either private_key or private_key_path required")

        # Initialize JWKS client
        self._jwks_client = PyJWKClient(
            self.JWKS_URL,
            cache_keys=True,
            lifespan=86400,  # Apple keys change rarely, cache for 24h
        )

        logger.info(f"AppleProvider initialized: team={team_id}, client={client_id}")

    def _generate_client_secret(self) -> str:
        """Generate client secret JWT for Apple.

        Apple's client_secret is a JWT signed with your private key.

        Returns:
            JWT client secret (valid for 6 months max)

        Evidence:
            From example-app/utils/apple_jwt.py lines 30-60
        """
        now = int(time.time())
        exp = now + (86400 * 180)  # 180 days (max allowed)

        payload = {
            "iss": self.team_id,
            "iat": now,
            "exp": exp,
            "aud": "https://appleid.apple.com",
            "sub": self.client_id,
        }

        headers = {
            "kid": self.key_id,
            "alg": "ES256",
        }

        return jwt.encode(
            payload,
            self._private_key,
            algorithm="ES256",
            headers=headers,
        )

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        response_mode: str = "form_post",
        **kwargs,
    ) -> str:
        """Generate Apple authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes
            response_mode: "query" or "form_post" (recommended)
            **kwargs: Additional parameters

        Returns:
            Authorization URL

        Note:
            Apple recommends response_mode="form_post" for security.
            The callback will be a POST request with the authorization code.

        Evidence:
            From example-app/endpoints/oauth.py Apple authorization
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "response_mode": response_mode,
        }
        params.update(kwargs)

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code
            redirect_uri: Callback URL

        Returns:
            Token response

        Raises:
            SSOAuthError: If exchange fails

        Evidence:
            From example-app/utils/apple_jwt.py token exchange
        """
        client_secret = self._generate_client_secret()

        data = {
            "client_id": self.client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        response = await self._post_form(self.TOKEN_URL, data)

        return SSOTokenResponse(
            access_token=response.get("access_token", ""),
            id_token=response.get("id_token"),
            refresh_token=response.get("refresh_token"),
            token_type=response.get("token_type", "Bearer"),
            expires_in=response.get("expires_in", 3600),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Get user info from Apple.

        Note: Apple doesn't have a userinfo endpoint.
        User info must be extracted from the ID token.

        Args:
            access_token: Not used for Apple

        Returns:
            Empty SSOUserInfo (use validate_id_token instead)
        """
        # Apple doesn't provide a userinfo endpoint
        # Information must come from the ID token
        logger.warning(
            "Apple doesn't provide userinfo endpoint. "
            "Use validate_id_token() to get user info from ID token."
        )
        return SSOUserInfo(provider_user_id="", raw_data={})

    def validate_id_token(
        self,
        id_token: str,
        user_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate and decode Apple ID token.

        Args:
            id_token: JWT ID token
            user_data: User data from authorization (name, email on first auth)

        Returns:
            Decoded token claims with user data merged

        Raises:
            SSOAuthError: If validation fails

        Note:
            Apple only sends user's name on FIRST authorization.
            The user_data parameter contains this data from the callback.

        Evidence:
            From example-app/utils/apple_jwt.py lines 95-180
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["ES256"],  # Apple uses ES256 (ECDSA)
                audience=self.client_id,
                issuer="https://appleid.apple.com",
            )

            # Merge user data if provided (from first authorization)
            if user_data:
                if "name" in user_data:
                    name_data = user_data["name"]
                    payload["given_name"] = name_data.get("firstName")
                    payload["family_name"] = name_data.get("lastName")
                    payload["name"] = f"{name_data.get('firstName', '')} {name_data.get('lastName', '')}".strip()

                if "email" in user_data:
                    payload["email"] = user_data["email"]

            # Check real_user_status (Apple-specific)
            # 0 = unsupported, 1 = unknown, 2 = likely real
            real_user = payload.get("real_user_status")
            if real_user is not None:
                payload["is_likely_real_user"] = real_user == 2

            return payload

        except jwt.ExpiredSignatureError:
            raise SSOAuthError("ID token has expired")
        except jwt.InvalidAudienceError:
            raise SSOAuthError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise SSOAuthError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise SSOAuthError(f"Invalid ID token: {e}")

    def extract_user_info(
        self,
        id_token_claims: Dict[str, Any],
    ) -> SSOUserInfo:
        """Extract SSOUserInfo from validated ID token claims.

        Args:
            id_token_claims: Claims from validate_id_token()

        Returns:
            Normalized user information
        """
        return SSOUserInfo(
            provider_user_id=id_token_claims.get("sub"),
            email=id_token_claims.get("email"),
            email_verified=id_token_claims.get("email_verified", False),
            name=id_token_claims.get("name"),
            given_name=id_token_claims.get("given_name"),
            family_name=id_token_claims.get("family_name"),
            raw_data=id_token_claims,
        )
```

---

## GitHub Provider

### Location

`/apps/kailash-nexus/src/nexus/auth/sso/github.py`

### Implementation

```python
"""GitHub OAuth2 SSO Provider.

Provides OAuth2 authentication with GitHub.

Note: GitHub uses OAuth2 but not OIDC (no ID token).
User info comes from the /user API endpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from .base import BaseSSOProvider, SSOAuthError, SSOTokenResponse, SSOUserInfo

logger = logging.getLogger(__name__)


class GitHubProvider(BaseSSOProvider):
    """GitHub OAuth2 provider.

    Usage:
        >>> from nexus.auth.sso import GitHubProvider
        >>>
        >>> github = GitHubProvider(
        ...     client_id="your-client-id",
        ...     client_secret="your-client-secret",
        ... )

    Endpoints:
        - Authorization: https://github.com/login/oauth/authorize
        - Token: https://github.com/login/oauth/access_token
        - User Info: https://api.github.com/user
        - Emails: https://api.github.com/user/emails

    Note:
        GitHub doesn't support OIDC/ID tokens. User information
        must be fetched from the API using the access token.
    """

    name = "github"

    # GitHub endpoints
    AUTHORIZATION_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USERINFO_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize GitHub provider.

        Args:
            client_id: OAuth App client ID
            client_secret: OAuth App client secret
            scopes: OAuth2 scopes (default: user:email)
            timeout: HTTP request timeout
        """
        super().__init__(client_id, client_secret, timeout)
        self.scopes = scopes or ["user:email"]

        logger.info("GitHubProvider initialized")

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        allow_signup: bool = True,
        **kwargs,
    ) -> str:
        """Generate GitHub authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes
            allow_signup: Allow new user signups (default: True)
            **kwargs: Additional parameters (login hint)

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "allow_signup": str(allow_signup).lower(),
        }
        params.update(kwargs)

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code
            redirect_uri: Callback URL

        Returns:
            Token response (no id_token for GitHub)

        Raises:
            SSOAuthError: If exchange fails
        """
        client = await self._get_http_client()

        # GitHub requires Accept header for JSON response
        response = await client.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            raise SSOAuthError(f"Token exchange failed: {response.text}")

        data = response.json()

        if "error" in data:
            raise SSOAuthError(f"GitHub error: {data.get('error_description', data['error'])}")

        return SSOTokenResponse(
            access_token=data["access_token"],
            id_token=None,  # GitHub doesn't provide ID tokens
            refresh_token=None,  # GitHub doesn't provide refresh tokens
            token_type=data.get("token_type", "Bearer"),
            expires_in=0,  # GitHub tokens don't expire
            scope=data.get("scope"),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user info from GitHub API.

        Args:
            access_token: OAuth2 access token

        Returns:
            Normalized user information
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Get basic user info
        user_data = await self._get_json(self.USERINFO_URL, headers=headers)

        # Get emails (if user:email scope granted)
        email = user_data.get("email")
        email_verified = False

        if not email:
            try:
                emails_data = await self._get_json(self.EMAILS_URL, headers=headers)
                # Find primary email
                for email_obj in emails_data:
                    if email_obj.get("primary"):
                        email = email_obj.get("email")
                        email_verified = email_obj.get("verified", False)
                        break
            except Exception as e:
                logger.warning(f"Failed to fetch GitHub emails: {e}")

        return SSOUserInfo(
            provider_user_id=str(user_data.get("id")),
            email=email,
            email_verified=email_verified,
            name=user_data.get("name"),
            given_name=None,  # GitHub doesn't provide separate names
            family_name=None,
            picture=user_data.get("avatar_url"),
            locale=None,
            raw_data=user_data,
        )

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """GitHub doesn't support ID tokens.

        Raises:
            SSOAuthError: Always, GitHub doesn't use OIDC
        """
        raise SSOAuthError(
            "GitHub doesn't support ID tokens. "
            "Use get_user_info() with the access token instead."
        )
```

---

## SSO Routes Integration

### Location

`/apps/kailash-nexus/src/nexus/auth/sso/__init__.py`

### Implementation

```python
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
"""

from .base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOProvider,
    SSOTokenResponse,
    SSOUserInfo,
)
from .azure import AzureADProvider
from .google import GoogleProvider
from .apple import AppleProvider
from .github import GitHubProvider

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
    # Helper functions
    "initiate_sso_login",
    "handle_sso_callback",
    "exchange_sso_code",
]


import secrets
from typing import Any, Dict, Optional
from fastapi import HTTPException
from fastapi.responses import RedirectResponse


import time
from typing import Dict

# In-memory state store with TTL (default implementation).
# PRODUCTION: Use Redis for distributed deployments:
#   redis_client.setex(f"sso_state:{state}", 600, json.dumps({"created_at": time.time()}))
_sso_state_store: Dict[str, float] = {}
_SSO_STATE_TTL_SECONDS = 600  # 10 minutes

def _cleanup_expired_states() -> None:
    """Remove expired states from in-memory store."""
    now = time.time()
    expired = [k for k, v in _sso_state_store.items() if now - v > _SSO_STATE_TTL_SECONDS]
    for k in expired:
        del _sso_state_store[k]

async def initiate_sso_login(
    provider: SSOProvider,
    callback_base_url: str,
    **kwargs,
) -> RedirectResponse:
    """Initiate SSO login flow.

    Args:
        provider: SSO provider instance
        callback_base_url: Base URL for callback (e.g., "https://myapp.com")
        **kwargs: Additional parameters for authorization URL

    Returns:
        Redirect response to provider's authorization page
    """
    # Generate CSRF state
    state = secrets.token_urlsafe(32)

    # Build callback URL
    redirect_uri = f"{callback_base_url}/auth/sso/{provider.name}/callback"

    # Get authorization URL
    auth_url = provider.get_authorization_url(
        state=state,
        redirect_uri=redirect_uri,
        **kwargs,
    )

    # Store state with creation timestamp for validation
    # In-memory store (development). For production, use Redis:
    #   await redis.setex(f"sso_state:{state}", _SSO_STATE_TTL_SECONDS, str(time.time()))
    _cleanup_expired_states()  # Periodic cleanup
    _sso_state_store[state] = time.time()

    return RedirectResponse(url=auth_url)


class InvalidStateError(Exception):
    """Raised when SSO state is invalid or expired."""
    pass


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
        HTTPException: If callback handling fails
        InvalidStateError: If CSRF state doesn't match or is expired
    """
    # Validate state against stored value (fail-closed: reject if not found)
    # In-memory store check. For production Redis:
    #   stored_time = await redis.get(f"sso_state:{state}")
    #   if stored_time is None:
    #       raise InvalidStateError("Invalid or expired SSO state")
    #   await redis.delete(f"sso_state:{state}")  # Single use
    stored_time = _sso_state_store.pop(state, None)
    if stored_time is None:
        raise InvalidStateError("Invalid or expired SSO state - possible CSRF attack")

    # Check if state has expired
    if time.time() - stored_time > _SSO_STATE_TTL_SECONDS:
        raise InvalidStateError("SSO state has expired - please try again")

    # Build redirect URI
    redirect_uri = f"{callback_base_url or ''}/auth/sso/{provider.name}/callback"

    try:
        # Exchange code for tokens
        tokens = await provider.exchange_code(code, redirect_uri)

        # Get or validate user info
        if tokens.id_token:
            claims = provider.validate_id_token(tokens.id_token)
            user_id = claims.get("sub")
            email = claims.get("email")
            name = claims.get("name")
        else:
            user_info = await provider.get_user_info(tokens.access_token)
            user_id = user_info.provider_user_id
            email = user_info.email
            name = user_info.name

        # Issue JWT using our auth plugin
        from nexus.auth.jwt import create_access_token

        access_token = create_access_token(
            auth_plugin,
            user_id=f"{provider.name}:{user_id}",
            email=email,
            roles=[],  # TODO: Map provider roles/groups
            provider=provider.name,
        )

        refresh_token = auth_plugin._jwt_middleware.create_refresh_token(
            user_id=f"{provider.name}:{user_id}",
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": auth_plugin.access_token_expire_minutes * 60,
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "provider": provider.name,
            },
        }

    except SSOAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSO callback failed: {e}")


async def exchange_sso_code(
    provider: SSOProvider,
    code: str,
    auth_plugin: Any,
    redirect_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange SSO code for tokens (SPA flow).

    For SPAs that handle the OAuth flow client-side and need to
    exchange the code for tokens via API.

    Args:
        provider: SSO provider instance
        code: Authorization code
        auth_plugin: NexusAuthPlugin instance
        redirect_uri: Redirect URI used in authorization

    Returns:
        JWT token response
    """
    return await handle_sso_callback(
        provider=provider,
        code=code,
        state="",  # No state validation for SPA flow
        auth_plugin=auth_plugin,
        callback_base_url=redirect_uri,
    )
```

---

## Configuration Examples

### Azure AD (Single Tenant)

```python
from nexus.auth import NexusAuthPlugin
from nexus.auth.sso import AzureADProvider

azure = AzureADProvider(
    tenant_id="12345678-1234-1234-1234-123456789012",
    client_id="your-client-id",
    client_secret="your-client-secret",
)

auth = NexusAuthPlugin(
    jwt_secret="your-jwt-secret",
    sso_providers=[azure],
    sso_callback_url="https://myapp.com",
)
```

### Azure AD (Multi-Tenant)

```python
azure = AzureADProvider(
    tenant_id="common",  # or "organizations"
    client_id="your-client-id",
    client_secret="your-client-secret",
    allowed_tenants=["tenant-1-id", "tenant-2-id"],  # Restrict to specific tenants
)
```

### Multiple Providers

```python
from nexus.auth.sso import AzureADProvider, GoogleProvider, AppleProvider, GitHubProvider

auth = NexusAuthPlugin(
    jwt_secret=os.getenv("JWT_SECRET"),
    sso_providers=[
        AzureADProvider(
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            client_id=os.getenv("AZURE_CLIENT_ID"),
            client_secret=os.getenv("AZURE_CLIENT_SECRET"),
        ),
        GoogleProvider(
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        ),
        AppleProvider(
            team_id=os.getenv("APPLE_TEAM_ID"),
            client_id=os.getenv("APPLE_CLIENT_ID"),
            key_id=os.getenv("APPLE_KEY_ID"),
            private_key_path=os.getenv("APPLE_PRIVATE_KEY_PATH"),
        ),
        GitHubProvider(
            client_id=os.getenv("GITHUB_CLIENT_ID"),
            client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
        ),
    ],
    sso_callback_url=os.getenv("APP_URL"),  # e.g., "https://myapp.com"
)
```

---

## Testing

### Unit Tests

```python
# tests/unit/auth/sso/test_providers.py
"""Unit tests for SSO providers."""

import pytest
from nexus.auth.sso import AzureADProvider, GoogleProvider


class TestAzureADProvider:
    """Test Azure AD provider."""

    def test_authorization_url_generation(self):
        """Test authorization URL is generated correctly."""
        azure = AzureADProvider(
            tenant_id="test-tenant",
            client_id="test-client",
            client_secret="test-secret",
        )

        url = azure.get_authorization_url(
            state="test-state",
            redirect_uri="https://myapp.com/callback",
        )

        assert "login.microsoftonline.com/test-tenant" in url
        assert "client_id=test-client" in url
        assert "state=test-state" in url
        assert "redirect_uri=https%3A%2F%2Fmyapp.com%2Fcallback" in url

    def test_multi_tenant_mode(self):
        """Test multi-tenant mode is detected."""
        azure = AzureADProvider(
            tenant_id="common",
            client_id="test-client",
            client_secret="test-secret",
        )

        assert azure.is_multi_tenant is True


class TestGoogleProvider:
    """Test Google provider."""

    def test_authorization_url_with_pkce(self):
        """Test authorization URL generation."""
        google = GoogleProvider(
            client_id="test.apps.googleusercontent.com",
            client_secret="test-secret",
        )

        url = google.get_authorization_url(
            state="test-state",
            redirect_uri="https://myapp.com/callback",
        )

        assert "accounts.google.com" in url
        assert "client_id=test.apps.googleusercontent.com" in url
```

### Integration Tests

```python
# tests/integration/auth/sso/test_azure_flow.py
"""Integration tests for Azure AD SSO flow."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_azure_sso_login_redirect():
    """Test SSO login redirects to Azure AD."""
    from nexus import Nexus
    from nexus.auth import NexusAuthPlugin
    from nexus.auth.sso import AzureADProvider

    app = Nexus(api_port=8003)
    auth = NexusAuthPlugin(
        jwt_secret="test-secret-32-characters-minimum",
        sso_providers=[
            AzureADProvider(
                tenant_id="test-tenant",
                client_id="test-client",
                client_secret="test-secret",
            ),
        ],
        sso_callback_url="http://localhost:8003",
    )
    app.add_plugin(auth)

    async with AsyncClient(
        app=app._gateway.app,
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        response = await client.get("/auth/sso/azure/login")

        assert response.status_code == 307  # Redirect
        assert "login.microsoftonline.com" in response.headers["location"]
```

---

## Security Considerations

### State Parameter (CSRF Protection)

Always validate the state parameter in callbacks:

```python
# Store state in session/cache before redirect
cache.set(f"sso_state:{state}", {"created_at": time.time()}, ttl=600)

# Validate state in callback
stored = cache.get(f"sso_state:{state}")
if not stored:
    raise HTTPException(status_code=400, detail="Invalid state parameter")
cache.delete(f"sso_state:{state}")  # One-time use
```

### Token Validation

Always validate tokens server-side:

- Verify signature using JWKS
- Check expiration (exp claim)
- Validate audience (aud claim = your client_id)
- Validate issuer (iss claim = expected provider)

### Multi-Tenant Security

For multi-tenant Azure AD apps:

- Always validate the tenant ID (tid claim)
- Maintain an allowlist of permitted tenants
- Consider per-tenant configuration

### Apple Sign-In Privacy

- Store user's name on first authorization (only sent once)
- Handle email relay addresses (@privaterelay.appleid.com)
- Check real_user_status for fraud detection
