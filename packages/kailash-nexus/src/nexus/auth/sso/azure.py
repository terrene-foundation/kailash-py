"""Azure AD (Microsoft Entra ID) SSO Provider.

Provides OAuth2/OIDC authentication with Microsoft Azure AD.

Supports:
    - Single-tenant and multi-tenant apps
    - JWKS-based token validation
    - User info from Microsoft Graph API

Evidence:
    - example-app: utils/azure_jwt.py (301 lines)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient
from nexus.auth.sso.base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOTokenResponse,
    SSOUserInfo,
)

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
    """

    name = "azure"

    AUTHORITY_BASE = "https://login.microsoftonline.com"
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
        allowed_tenants: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize Azure AD provider.

        Args:
            tenant_id: Azure AD tenant ID (or "common" for multi-tenant)
            client_id: Application (client) ID
            client_secret: Client secret
            scopes: OAuth2 scopes (default: openid, profile, email, User.Read)
            allowed_tenants: For multi-tenant apps, list of allowed tenant IDs
            timeout: HTTP request timeout
        """
        super().__init__(client_id, client_secret, timeout)
        self.tenant_id = tenant_id
        self.scopes = scopes or ["openid", "profile", "email", "User.Read"]
        self.allowed_tenants = allowed_tenants
        self.is_multi_tenant = tenant_id in ("common", "organizations", "consumers")

        self._jwks_client = PyJWKClient(
            f"{self.AUTHORITY_BASE}/{tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
            lifespan=3600,
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
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)

            if self.is_multi_tenant:
                unverified = jwt.decode(id_token, options={"verify_signature": False})
                tid = unverified.get("tid")
                if self.allowed_tenants and tid not in self.allowed_tenants:
                    raise SSOAuthError(f"Tenant {tid} not in allowed list")
                issuer = f"{self.AUTHORITY_BASE}/{tid}/v2.0"
            else:
                issuer = f"{self.AUTHORITY_BASE}/{self.tenant_id}/v2.0"

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=issuer,
            )

            return payload

        except SSOAuthError:
            raise
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
